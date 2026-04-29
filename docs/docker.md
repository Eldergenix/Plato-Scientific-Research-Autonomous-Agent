# Docker

You can run Denario in a [Docker](https://www.docker.com/) image, which includes all the required dependencies for Denario including LaTeX.

## Pull a Docker image

You can get a Docker image from the [Docker Hub](https://hub.docker.com/r/pablovd/denario). Pull the image with:

```bash
docker pull pablovd/denario:latest
```

Once built, you can run the GUI with

```bash
docker run -p 8501:8501 --rm pablovd/denario:latest
```

where we indicate the port `8501`. We can also run a container in interactive mode, so you can access through the terminal to the container, with

```bash
docker run --rm -it pablovd/denario:latest bash
```

Share volumes with `-v $(pwd)/project:/app/project` for inputing data and accessing to it. You can also share the API keys with a `.env` file in the same folder with `-v $(pwd).env/app/.env`. A container example with these both volumes would be like this:

```bash
docker run --rm \
  -p 8501:8501 \
  -v $(pwd)/project:/app/project \
  -v $(pwd).env/app/.env \
  denario_src
```

## Build a Docker image from source

If you build Denario from source and want to build a local image, we can do it running this line from the root of Denario:

```bash
docker build -f docker/Dockerfile.dev -t denario_src .
```

And then run a container with the commands above, indicating the name of the image `denario_src` and sharing as a volume the current path to allow that the changes in the code are reflected automatically:

- GUI

```bash
docker run --rm \
  -p 8501:8501 \
  -v "$(pwd)":/app \
  denario_src
```

- Interactive (terminal)

```bash
docker run -it --rm \
  -v "$(pwd)":/app \
  denario_src bash
```

## Run with Docker compose

A simpler way to run the local image is with [Docker Compose](https://docs.docker.com/compose/), which already sets the volumes to be shared in the yaml settings file. Ensure that you have [installed Docker Compose](https://docs.docker.com/compose/install) and run the following commands for using Denario:

- GUI

```bash
docker compose up
```

or

```bash
docker compose run --rm denario
```

- Interactive (terminal)

```bash
docker compose run --rm denario bash
```
