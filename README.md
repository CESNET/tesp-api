# TESP API

[![GitHub issues](https://img.shields.io/github/issues/CESNET/tesp-api)](https://github.com/CESNET/tesp-api/issues)
[![poetry](https://img.shields.io/badge/maintained%20with-poetry-informational.svg)](https://python-poetry.org/)
[![python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/download)
[![last-commit](https://img.shields.io/github/last-commit/CESNET/tesp-api)]()

This project is an effort to create Open-source implementation of a task execution engine based on the [TES standard](https://github.com/ga4gh/task-execution-schemas)
distributing executions to services exposing [Pulsar](https://github.com/galaxyproject/pulsar) application. For more details
on `TES`, see the Task Execution Schemas [documentation](https://ga4gh.github.io/task-execution-schemas/docs/). `Pulsar`
is a Python server application that allows a [Galaxy](https://github.com/galaxyproject/galaxy) server to run jobs on remote systems. The original intention of this
project was to modify the `Pulsar` project (e.g. via forking) so its Rest API would be compatible with the `TES` standard.
Later a decision was made that rather a separate microservice will be created, decoupled from the `Pulsar`, implementing the `TES`
standard and distributing `TES` tasks execution to `Pulsar` applications.

## Quick start

### Deploy
The most straightforward way to deploy the TESP is to use Docker Compose.

#### All services (default):
```
docker compose --profile all up -d
```

#### Without pulsar_rest service:
```
docker compose --profile api up -d
```

#### Only pulsar_rest service:
```
docker compose --profile pulsar up -d
```
<br />
<br />
<br />

Depending on you Docker and Docker Compose installation, you may need to use `docker-compose` (with hyphen) instead.

You might encounter a timeout error in container runtime which can be solved by correct `mtu` configuration either in the `docker-compose.yaml`:
```
networks:
  default:
    driver: bridge
    driver_opts:
      com.docker.network.driver.mtu: 1442
```
 or directly in your `/etc/docker/daemon.json`:
```
{
	"mtu": 1442
}
```

The `docker-compose.yaml` spins also collection of [Data Transfer Services](docker/dts/README.md) which can be used for testing. 

### Usage
If the TESP is running, you can try to submit a task. One way is to use cURL. Although the project is still in development, the TESP should be compatible with TES so you can try TES clients such as Snakemake or Nextflow. The example below shows how to submit task using cURL.

#### 1. Create JSON file
The first step you need to take is to prepare JSON file with the task. For inspiration you can use [tests](https://github.com/CESNET/tesp-api/tree/dev/tests/test_jsons) located in this repository, or [TES documentation](https://ga4gh.github.io/task-execution-schemas/docs/).  

Example JSON file:
```
{
  "inputs": [
    {
      "url": "http://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.5.5.tar.xz",
      "path": "/data/kernel.tar.gz",
      "type": "FILE"
    }
  ],
  "executors": [
    {
      "image": "ubuntu:20.04",
      "command": [
        "/bin/sha1sum",
        "./kernel.tar.gz"
      ],
      "workdir": "/data/",
      "stdout": "/tmp/stdout.log",
      "stderr": "/tmp/stderr.log"
    }
  ]
}
```
#### 2. Submit task
Please check the URL of the running TES and the file with the task you just created.
```
curl http://localhost:8080/v1/tasks -X POST -H "Content-Type: application/json" -d $(sed -e "s/ //g" example.json | tr -d '\n')
```
(The only reason for the subshell is to remove whitespaces and newlines.)  
After the task is submitted, the endpoint returns the task ID. This is usefull to check the task status.

#### 3. Check the task status
There are more usefull endpoints to check the task status.  

List all tasks:
```
curl "http://localhost:8080/v1/tasks"
```

Check the specific task status (enter your task ID):
```
curl "http://localhost:8080/v1/tasks/<id>?view=FULL"
```


&nbsp;
## Getting Started
Repository contains `docker-compose.yaml` file with infrastructure setup for current functionality which can be used to
immediately start the project in **DEVELOPMENT** environment. This is convenient for users and contributors as there is no need to manually install and
configure all the services which `TESP API` requires for it to be fully functional. While this is the easiest approach to start
the project, for "first timers" it's recommended to follow this readme to understand all the services and tools used across the project.  
**Also have a detailed look at [Current Docker services](#current-docker-services) section of this readme before starting up the infrastructure for the first time**.
  
_**!! DISCLAIMER**_:  
Project is currently in the development phase only and should not be used in production environments yet. If you really
wish to set up a production environment despite missing features, tests etc ... then following contents will show what needs to be done.  

### Requirements
_You can work purely with [docker](https://www.docker.com/) and [docker-compose](https://docs.docker.com/compose/) only
instead of starting the project locally without `docker`. In that case only those two dependencies are relevant for you._

| dependency     | version  | note                                                                                                                                                          |
|----------------|:--------:|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| docker         | 20.10.0+ | _**latest** is preferred_                                                                                                                                     |
| docker-compose | 1.28.0+  | -                                                                                                                                                             |  
| python         | 3.10.0+  | -                                                                                                                                                             |
| pip            | python3  | _**21.3.1** in case of problems_                                                                                                                              |
| poetry         | 1.1.13+  | _pip install poetry_                                                                                                                                          |
| mongodb        |   4.4+   | _docker-compose uses latest_                                                                                                                                  |
| pulsar         | 0.14.13  | _actively trying to support latest. Must have access to docker with the same host as pulsar application itself_                                               |
| ftp server     |    -     | _no real recommendation here. docker-compose uses [ftpserver](https://github.com/fclairamb/ftpserver) so local alternative should support same fpt commands_. |  

### Configuring TESP API
`TESP API` uses [dynaconf](https://www.dynaconf.com/) for its configuration. Configuration is currently set up by using
[./settings.toml](https://github.com/CESNET/tesp-api/blob/main/settings.toml) file. This file declares sections which represent different environments for `TESP API`. Default section
is currently used for local development without `docker`. Also, all the properties from default section are propagated
to other sections as well unless they are overridden in the specific section itself. So for example if following `settings.toml`
file is used
```
[default]
db.mongodb_uri = "mongodb://localhost:27017"
logging.level = "DEBUG"

[dev-docker]
db.mongodb_uri = "mongodb://tesp-db:27017"
```
then dev-docker environment will use property `logging.level = DEBUG` as well, while property `db.mongodb_uri`
gets overridden to url of mongodb in the docker environment. `dev-docker` section in current [./settings.toml](https://github.com/CESNET/tesp-api/blob/main/settings.toml)
file is set up to support [./docker-compose.yaml](https://github.com/CESNET/tesp-api/blob/main/docker-compose.yaml) for development infrastructure.  
To apply different environment (i.e. to switch which section will be picked by `TESP API`) environment variable
`FASTAPI_PROFILE` must be set to the concrete name of such section (e.g. `FASTAPI_PROFILE=dev-docker` which can be seen
in the [./docker/tesp_api/Dockerfile](https://github.com/CESNET/tesp-api/blob/main/docker/tesp_api/Dockerfile))  

### Configuring required services
You can have a look at [./docker-compose.yaml](https://github.com/CESNET/tesp-api/blob/main/docker-compose.yaml) to see how
the infrastructure for development should look like. Of course, you can configure those services in your preferred way if you are
going to start the project without `docker` or if you are trying to create other than `development` environment but some things
must remain as they are. For example, `TESP API` currently supports communication with `Pulsar` only through its Rest API and
therefore `Pulsar` must be configured in such a way.

### Current Docker services
All the current `Docker` services which will be used when the project is started with `docker-compose` have common directory
[./docker](https://github.com/CESNET/tesp-api/tree/main/docker) for configurations, data, logs and Dockerfiles if required.
`docker-compose` should run out of the box, but sometimes it might happen that a problem with privileges occurs while for
example trying to create data folder for given service. Such issues should be resolved easily manually. Always look into
[./docker-compose.yaml](https://github.com/CESNET/tesp-api/blob/main/docker-compose.yaml) to see what directories need to mapped
which ports to be used etc. Following services are currently defined by [./docker-compose.yaml](https://github.com/CESNET/tesp-api/blob/main/docker-compose.yaml)
- **tesp-api** - This project itself. Depends on mongodb
- **tesp-db**  - [MongoDB](https://www.mongodb.com/) instance for persistence layer
- **pulsar_rest** - `Pulsar` configured to use Rest API with access to a docker instance thanks to [DIND](https://hub.docker.com/_/docker).
- **pulsar_amqp** - currently disabled, will be used in the future development
- **ftpserver** - online storage for `TES` tasks input/output content
- **minio** - currently acting only as a storage backend for the `ftpserver` with simple web interface to access data.  

**Folder [./docker/minio/initial_data](https://github.com/CESNET/tesp-api/tree/main/docker/minio/initial_data) contains startup
folders for `minio` service which must be copied to the `./docker/minio/data` folder before starting up the infrastructure. Those data
configure `minio` to start with already created bucket and user which will be used by `ftpserver` for access.**  

### Run the project
This project uses [Poetry](https://python-poetry.org/) for `dependency management` and `packaging`. `Poetry` makes it easy
to install libraries required by `TESP API`. It uses [./pyproject.toml](https://github.com/CESNET/tesp-api/blob/feature/TESP-0-github-proper-readme/pyproject.toml)
file to obtain current project orchestration configuration. `Poetry` automatically creates virtualenv, so it's easy to run
application immediately. You can use command `poetry config virtualenvs.in-project true` which **globally** configures
creation of virtualenv directories directly in the project instead of the default cache folder. Then all you need to do
to run `TESP API` deployed to `uvicorn` for example is:
```shell
poetry install
poetry run uvicorn tesp_api.tesp_api:app --reload --host localhost --port 8000
```
Otherwise, as was already mentioned, you can instead use `docker-compose` to start whole **development** infrastructure.
Service representing `TESP API` is configured to mount this project sources as a volume and `TESP API` is run with the very
same command as is mentioned above. Therefore, any changes made to the sources in this repository will be immediately applied to the docker
service as well, enabling live reloading which makes development within the `docker` environment very easy.
```shell
docker-compose up -d
```

&nbsp;
## Exploring the functionality
`docker-compose` sets up whole development infrastructure. There will be two important endpoints to explore if you wish to
execute some `TES` tasks. Before doing any action, don't forget to run `docker-compose logs` command to see if each service
initialized properly or whether any errors occurred.

- **http://localhost:8080/** - will redirect to Swagger documentation of `TESP API`. This endpoint also currently acts as a frontend.
You can use it to execute REST based calls expected by the `TESP API`. Swagger is automatically generated from the sources,
and therefore it corresponds to the very current state of the `TESP API` interface.
- **http://localhost:40949/** - `minio` web interface. Use `admin` and `!Password123` credentials to login. Make sure
that bucket `tesp-ftp` is already present, otherwise see [Current Docker services](#current-docker-services) section of this readme to properly
prepare infrastructure before the startup.

### Executing simple TES task
This section will demonstrate execution of simple `TES` task which will calculate _[md5sum](https://en.wikipedia.org/wiki/Md5sum)_
hash of given input. There are more approaches of how I/O can be handled by `TES` but main goal here is to demonstrate `ftp server` as well.  

1. Head over to **http://localhost:40949/buckets/tesp-ftp/browse** and upload a new file with your preferred name and content (e.g. name
`holy_file` and content `Hello World!`). This file will now be accessible trough `ftpserver` service and will be used as
an input file for this demonstration.
2. Go to **http://localhost:8080/** and use `POST /v1/tasks` request to create following `TES` task (task is sent in the request body).
In the `"inputs.url"` replace `<file_uploaded_to_minio>` with the file name you chose in the previous step. If http status of
returned response is 200, the response will contain `id` of created task in the response body which will be used to
reference this task later on.
```json
{
  "inputs": [
    {
      "url": "ftp://ftpserver:2121/<file_uploaded_to_minio>",
      "path": "/data/file1",
      "type": "FILE"
    }
  ],
  "outputs": [
    {
      "path": "/data/outfile",
      "url": "ftp://ftpserver:2121/outfile-1",
      "type": "FILE"
    }
  ],
  "executors": [
    {
      "image": "alpine",
      "command": [
        "md5sum"
      ],
      "stdin": "/data/file1",
      "stdout": "/data/outfile"
    }
  ]
}
```
3. Use `GET /v1/tasks/{id}` request to view task you have created. Use `id` from the response you have obtained in the
previous step. This request also supports `view` query parameter which can be used to limit the view of the task. By default,
`TESP API` will return `MINIMAL` view which only includes `id` and `state` of the requested task. Wait until task state is
set to the state `COMPLETE` or one of the error states. In case of an error state, depending on its type, the error will be part
of the task logs in the response (use `FULL` view), or you can inspect the logs of `TESP API` service, where error should be logged with respective
message.
4. Once the task completes you can head over back to **http://localhost:40949/buckets/tesp-ftp/browse** where you should find
uploaded `outfile-1` with output content of executed _[md5sum](https://en.wikipedia.org/wiki/Md5sum)_. You can play around
by creating different tasks, just be sure to only use functionality which is currently supported - see [Known limitations](#known-limitations).
For example, you can omit `inputs.url` and instead use `inputs.content` which allows you to create input in place, or you can also
omit `outputs` and `executors.stdout` in which case the output will be present in the `logs.logs.stdout` as executor is no
longer configured to redirect stdout into the file.  

### Known limitations of TESP API
| Domain   | Limitation                                                                                                                                                                         |
|----------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| _Pulsar_ | `TESP API` communicates with `Pulsar` only through its REST API, missing functionality for message queues                                                                          |
| _Pulsar_ | `TESP API` should be able to dispatch executions to multiple `Pulsar` services via different types of `Pulsar` interfaces. Currently, only one `Pulsar` service is supported       |
| _Pulsar_ | `Pulsar` must be "polled" for job state. Preferably `Pulsar` should notify `TESP API` about state change. This is already default behavior when using `Pulsar` with message queues |
| _TES_    | Canceling `TES` task does not immediately stop the task. Task even cannot be canceled while it is running.                                                                         |
| _TES_    | `TES` does not state specific urls to be supported for file transfer (e.g. tasks `inputs.url`). Only FTP is supported for now                                                      |
| _TES_    | tasks `inputs.type` and `outputs.type` can be either DIRECTORY or FILE. Only FILE is supported, DIRECTORY will lead to undefined behavior for now                                  |
| _TES_    | tasks `resources` currently do not change execution behavior in any way. This configuration will take effect once `Pulsar` limitations are resolved                                |
| _TES_    | tasks `executors.workdir` and `executors.env` functionality is not yet implemented. You can use them but they will have no effect                                                  |
| _TES_    | tasks `volumes` and `tags` functionality is not yet implemented. You use them but they will have no effect                                                                         |
| _TES_    | tasks `logs.outputs` functionality is not yet implemented. However this limitation can be bypassed with tasks `outputs`                                                            |

&nbsp;
## GIT
Current main branch is `origin/main`. This happens to be also a release branch for now. Developers should typically derive their
own feature branches such as e.g. `feature/TESP-111-task-monitoring`. This project has not yet configured any CI/CD. Releases are
done manually by creating a tag in the current release branch. There is not yet configured any issue tracking software but for
any possible future integration this project should reference commits, branches PR's etc ... with prefix `TESP-0` as a reference
to a work that has been done before such integration. Pull request should be merged using `Squash and merge` option with message format `Merge pull request #<PRnum> from <branch-name>`.
Since there is no CI/CD setup this is only opinionated view on how branching policies should work and for now everything is possible. 

## License

[![license](https://img.shields.io/github/license/CESNET/tesp-api)](https://github.com/CESNET/tesp-api/blob/main/LICENSE.md)
```
Copyright (c) 2022 Norbert Dopjera

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
