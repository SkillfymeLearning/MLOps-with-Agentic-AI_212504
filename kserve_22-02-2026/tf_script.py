def mnist_dist_train_logic():
    import tensorflow as tf
    import numpy as np
    import os, json, time
    import boto3
    from urllib.parse import urlparse
    from tensorflow import keras
    from sklearn.metrics import confusion_matrix

    # ─── S3 Helpers ───────────────────────────────────────────────────────────

    def get_s3_client():
        return boto3.client(
            's3',
            endpoint_url=os.getenv('S3_ENDPOINT'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )

    s3 = get_s3_client()

    def download_s3(s3_uri, local_path):
        parsed = urlparse(s3_uri)
        s3.download_file(parsed.netloc, parsed.path.lstrip('/'), local_path)

    def upload_s3(local_path, s3_uri):
        parsed = urlparse(s3_uri)
        bucket, key = parsed.netloc, parsed.path.lstrip('/')
        if os.path.isdir(local_path):
            for root, _, files in os.walk(local_path):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, local_path)
                    s3.upload_file(full_p, bucket, os.path.join(key, rel_p))
        else:
            s3.upload_file(local_path, bucket, key)

    def s3_key_exists(s3_uri):
        parsed = urlparse(s3_uri)
        try:
            s3.head_object(Bucket=parsed.netloc, Key=parsed.path.lstrip('/'))
            return True
        except Exception:
            return False

    # ─── 1. Strategy & Role Identification ────────────────────────────────────

    strategy = tf.distribute.MultiWorkerMirroredStrategy()

    tf_config = json.loads(os.environ.get('TF_CONFIG', '{}'))
    task = tf_config.get('task', {})
    task_type  = task.get('type', 'worker')
    task_index = task.get('index', 0)
    is_chief   = (task_type == 'worker' and task_index == 0)

    print(f'[INFO] task_type={task_type} task_index={task_index} is_chief={is_chief}', flush=True)

    # ─── 2. Load Data ─────────────────────────────────────────────────────────

    download_s3(os.environ['X_TRAIN_URI'], 'x_train.npy')
    download_s3(os.environ['Y_TRAIN_URI'], 'y_train.npy')
    download_s3(os.environ['X_TEST_URI'],  'x_test.npy')
    download_s3(os.environ['Y_TEST_URI'],  'y_test.npy')

    x_train = np.load('x_train.npy').astype(np.float32)
    y_train = np.load('y_train.npy').astype(np.int64)
    x_test  = np.load('x_test.npy').astype(np.float32)
    y_test  = np.load('y_test.npy').astype(np.int64)

    # ─── 3. Distributed Datasets ──────────────────────────────────────────────

    global_batch_size = 16 * strategy.num_replicas_in_sync

    options = tf.data.Options()
    options.experimental_distribute.auto_shard_policy = tf.data.experimental.AutoShardPolicy.OFF

    def make_train_ds():
        def gen():
            idx = np.random.permutation(len(x_train))
            for i in range(0, len(idx) - global_batch_size, global_batch_size):
                b = idx[i:i + global_batch_size]
                yield x_train[b], y_train[b]
        return tf.data.Dataset.from_generator(
            gen,
            output_signature=(
                tf.TensorSpec(shape=(None, 28, 28, 1), dtype=tf.float32),
                tf.TensorSpec(shape=(None,),           dtype=tf.int64),
            )
        ).prefetch(tf.data.AUTOTUNE)

    def make_test_ds():
        def gen():
            for i in range(0, len(x_test), global_batch_size):
                yield x_test[i:i + global_batch_size], y_test[i:i + global_batch_size]
        return tf.data.Dataset.from_generator(
            gen,
            output_signature=(
                tf.TensorSpec(shape=(None, 28, 28, 1), dtype=tf.float32),
                tf.TensorSpec(shape=(None,),           dtype=tf.int64),
            )
        ).prefetch(tf.data.AUTOTUNE)

    # ─── 4. Load & Compile Model Inside Strategy Scope ────────────────────────

    download_s3(os.environ['MODEL_URI'], 'model.keras')

    with strategy.scope():
        model = keras.models.load_model('model.keras')
        model.compile(
            optimizer=tf.keras.optimizers.SGD(learning_rate=float(os.environ['LEARNING_RATE'])),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )

    # ─── 5. Train & Evaluate (Collective Ops) ─────────────────────────────────

    print(f'[INFO] task={task_index} starting fit', flush=True)
    model.fit(make_train_ds(), epochs=1, verbose=1)
    
    print(f'[INFO] task={task_index} starting eval', flush=True)
    loss, acc = model.evaluate(make_test_ds(), verbose=1)
    print(f'[INFO] task={task_index} Eval — loss: {loss:.4f}, accuracy: {acc:.4f}', flush=True)

    # ─── 6. Post-Training & Sentinel Logic ────────────────────────────────────

    model_trained_uri = os.environ['TRAINED_MODEL_URI']
    base_uri = model_trained_uri.rsplit('/', 2)[0]
    trained_model_uri = model_trained_uri + '/1'
    sentinel_uri = base_uri + '/chief_done.txt'
    print(f'[INFO] base_uri={base_uri} sentinel_uri={sentinel_uri} model_trained_uri={model_trained_uri}', flush=True)

    if is_chief:
        # Save weights from the distributed model to a temporary file
        temp_weights = '/tmp/weights_sync.h5'
        model.save_weights(temp_weights)
        
        # IMPORTANT: Load a FRESH model outside the strategy scope.
        # This prevents model.predict() from trying to sync with workers.
        with tf.device('/CPU:0'):
            standalone_model = keras.models.load_model('model.keras')
            standalone_model.load_weights(temp_weights)
            
            print('[INFO] Chief: Exporting model (standalone)...', flush=True)
            base_export_dir = '/tmp/export'
            version_dir = os.path.join(base_export_dir, '1')
            os.makedirs(version_dir, exist_ok=True)
            # Export the model to version_dir (Keras 3)
            standalone_model.export(version_dir)
            # Upload all files in /tmp/export/1/ to S3
            upload_s3(version_dir, trained_model_uri)

            print('[INFO] Chief: Generating predictions (standalone)...', flush=True)
            y_pred_logits = standalone_model.predict(x_test, batch_size=64, verbose=0)
            y_pred = np.argmax(y_pred_logits, axis=1)
            cmatrix = confusion_matrix(y_test, y_pred).tolist()

        # Metrics and Metadata
        metrics_data = {'accuracy': float(acc), 'loss': float(loss)}
        with open('meta.json', 'w') as f:
            json.dump({'metrics': metrics_data, 'cmatrix': cmatrix}, f, indent=2)
        upload_s3('meta.json', os.environ['METRICS_JSON_URI'])

        # Signal workers to exit
        with open('/tmp/chief_done.txt', 'w') as f:
            f.write('done')
        upload_s3('/tmp/chief_done.txt', sentinel_uri)
        print('[INFO] Chief: Sentinel uploaded. All clear.', flush=True)

    else:
        # Polling logic for workers
        print(f'[INFO] task={task_index}: Waiting for chief sentinel...', flush=True)
        for attempt in range(150): # ~5 minutes
            if s3_key_exists(sentinel_uri):
                print(f'[INFO] task={task_index}: Sentinel found, exiting.', flush=True)
                break
            time.sleep(2)
        else:
            print(f'[WARN] task={task_index}: Sentinel timeout, exiting anyway.', flush=True)

    print(f'[INFO] task={task_index} Done.', flush=True)