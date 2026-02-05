# Qdrant Docker Helper

## Run Qdrant

Run Qdrant with default ports:

```bash
docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  qdrant/qdrant
```

Run Qdrant with a bind-mounted storage directory:

```bash
mkdir -p /path/to/qdrant_storage

docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v /path/to/qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

Run Qdrant with a different container name:

```bash
docker run -d --name my-qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  qdrant/qdrant
```



***

## Check if Qdrant is running

Show running Qdrant containers:

```bash
docker ps --filter "name=qdrant"
```

Check by name and show status only:

```bash
docker inspect -f '{{.State.Status}}' qdrant
# expected: "running" | "exited" | "created"
```

Simple grep-based check:

```bash
docker ps | grep qdrant
```



***

## Check Qdrant container size

Show size of the `qdrant` container:

```bash
docker ps --filter "name=qdrant" --size
```



***

## Start, stop, and restart Qdrant

Start an existing container:

```bash
docker start qdrant
```

Stop a running container:

```bash
docker stop qdrant
```

Restart:

```bash
docker restart qdrant
```



***

## Remove and recreate Qdrant

Stop and remove container:

```bash
docker stop qdrant
docker rm qdrant
```

Remove Qdrant image (optional, to pull fresh):

```bash
docker rmi qdrant/qdrant
```

Recreate with the original run command:

```bash
docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  qdrant/qdrant
```



***

## One-liner: recreate Qdrant

Stop, remove, and recreate in one go:

```bash
docker rm -f qdrant || true

docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  qdrant/qdrant
```



***

## Check Qdrant logs

Tail logs:

```bash
docker logs -f qdrant
```

Show last 100 lines:

```bash
docker logs --tail 100 qdrant
```


***

## Migrate existing Qdrant data from Docker's internal storage to an external drive

1) Create a directory on the external drive  
2) Start a new Qdrant container with that directory bind-mounted to `/qdrant/storage`  
3) Copy the old data into the new mount (or re-index if you prefer)

Here's a Markdown-style snippet with concrete commands.

***

## Migrate Qdrant data to external drive

### 1. Prepare external drive directory

Assume your external drive is mounted at `/Volumes/ExternalHDD`:

```bash
mkdir -p /Volumes/ExternalHDD/qdrant_storage
```



***

### 2. Stop existing Qdrant container

```bash
docker stop qdrant
```

(Optional, back up Docker's existing data directory if you know its path.)

***

### 3. Start Qdrant with external storage bind mount

Start a new container that uses the external drive for `/qdrant/storage`:

```bash
docker rm qdrant || true

docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v /Volumes/ExternalHDD/qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

`/qdrant/storage` is where Qdrant persists all data, so mounting it redirects storage to your external drive. [github](https://github.com/orgs/qdrant/discussions/4129)

***

### 4. Option A – Copy old data into the new mount (if you can locate it)

If you know the original Docker-managed storage directory (example path, will vary per system):

```bash
# Example only – adjust OLD_PATH to your actual location
OLD_PATH="/path/to/old/qdrant/storage"

sudo cp -a "${OLD_PATH}/." /Volumes/ExternalHDD/qdrant_storage/
```

Then restart Qdrant:

```bash
docker restart qdrant
```



***

### 5. Option B – Re-index into new Qdrant

If you don't want to hunt for the old storage directory, you can:

1. Start the new Qdrant container with the external mount (step 3).  
2. Re-run your `ingest_pdf.py` / indexing pipeline to repopulate Qdrant; data will now be written to `/Volumes/ExternalHDD/qdrant_storage`. [qdrant](https://qdrant.tech/documentation/quickstart/)

***

### 6. Verify migration

Check that Qdrant is running:

```bash
docker ps --filter "name=qdrant"
```

Check that data is being written to the external drive:

```bash
du -sh /Volumes/ExternalHDD/qdrant_storage
```