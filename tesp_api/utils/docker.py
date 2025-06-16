import os
import shlex
from urllib.parse import urlparse
from typing import Dict, List, Tuple

from pymonad.maybe import Nothing, Maybe, Just

from tesp_api.repository.model.task import TesTaskExecutor, TesTaskOutput, TesTaskIOType
from tesp_api.utils.functional import get_else_throw, maybe_of


class DockerRunCommandBuilder:

    def __init__(self) -> None:
        self._job_id: str = ""
        self._resource_cpu: Maybe[str] = Nothing
        self._resource_mem: Maybe[str] = Nothing
        self._docker_image: Maybe[str] = Nothing
        self._workdir: Maybe[str] = Nothing
        self._envs: Dict[str, str] = {}
        self._volumes: Dict[str, str] = {}
        self._bind_mounts: Dict[str, str] = {}
        self._command: Maybe[str] = Nothing

    def with_job_id(self, job_id: str):
        self._job_id = job_id
        return self

    def with_resource(self, resources: dict):
        if not resources: return self
        self._resource_cpu = maybe_of(resources["cpu_cores"])
        self._resource_mem = maybe_of(resources["ram_gb"])
        return self

    def with_bind_mount(self, container_path: str, host_path: str):
        self._bind_mounts[container_path] = host_path
        return self

    def with_volume(self, container_path: str, volume_name: str):
        self._volumes[container_path] = volume_name
        return self

    def with_image(self, image: str):
        self._docker_image = Just(image)
        return self

    def with_workdir(self, workdir: str):
        self._workdir = maybe_of(workdir)
        return self

    def with_env(self, name: str, value: str):
        self._envs[name] = value
        return self

    def with_command(self, command: List[str], stdin: Maybe[str] = Nothing,
                     stdout: Maybe[str] = Nothing, stderr: Maybe[str] = Nothing):
        command_str = " ".join(command)
        self._command = Just(command_str) if command_str else Nothing

        # sh -c '' # there probably must be ' instead of " because of the passing unresolved envs into the container
        self._command = self._command.map(lambda _command:
                                          f'{_command}'
                                          f'{stdin.maybe("", lambda x: " <" + x)}'
                                          f'{stdout.maybe("", lambda x: " 1>" + x)}'
                                          f'{stderr.maybe("", lambda x: " 2>" + x)}')
        return self

    def reset(self) -> None:
        self._resource_cpu = Nothing
        self._resource_mem = Nothing
        self._docker_image = Nothing
        self._workdir = Nothing
        self._volumes = {}
        self._bind_mounts = {}
        return self

    def get_run_command(self) -> str:
        resources_str = (f'{self._resource_cpu.maybe("", lambda cpu: " --cpus="+str(cpu))}'
                         f'{self._resource_mem.maybe("", lambda mem: " --memory="+str(mem)+"g")}')
        bind_mounts_str = " ".join(map(lambda v_paths: f'-v \"{v_paths[1]}\":\"{v_paths[0]}\"', self._bind_mounts.items()))
        volumes_str     = " ".join(map(lambda v_paths: f'-v \"{v_paths[1]}\":\"{v_paths[0]}\"', self._volumes.items()))
        docker_image    = get_else_throw(self._docker_image, ValueError('Docker image is not set'))
        workdir_str     = self._workdir.maybe("", lambda workdir: f"-w=\"{str(workdir)}\"")
        env_str         = " ".join(map(lambda env: f'-e {env[0]}=\"{env[1]}\"', self._envs.items()))
        command_str = self._command.maybe("", lambda x: x)

        run_command = f'docker run {resources_str} {workdir_str} {env_str} {volumes_str} {bind_mounts_str} {docker_image} {command_str}'
        self.reset()
        return run_command

    def get_run_command_script(self, inputs_directory: str, i: int) -> Tuple[str, str]:
        resources_str = (f'{self._resource_cpu.maybe("", lambda cpu: " --cpus="+str(cpu))}'
                         f'{self._resource_mem.maybe("", lambda mem: " --memory="+str(mem)+"g")}')
        bind_mounts_str = " ".join(map(lambda v_paths: f'-v \"{v_paths[1]}\":\"{v_paths[0]}\"', self._bind_mounts.items()))
        volumes_str     = " ".join(map(lambda v_paths: f'-v \"{v_paths[1]}\":\"{v_paths[0]}\"', self._volumes.items()))
        docker_image    = get_else_throw(self._docker_image, ValueError('Docker image is not set'))
        workdir_str     = self._workdir.maybe("", lambda workdir: f"-w=\"{str(workdir)}\"")
        volumes_str    += f' -v "{inputs_directory}/run_script_{i}.sh":"/tmp/{self._job_id}/run_script_{i}.sh"'
        env_str         = " ".join(map(lambda env: f'-e {env[0]}=\"{env[1]}\"', self._envs.items()))
        command_str = self._command.maybe("", lambda x: x)

        chmod_commands = f"chmod +x /tmp/{self._job_id}/run_script_{i}.sh"
        if self._bind_mounts:
            chmod_commands += ' && ' + ' && '.join(f"chmod +x {key}" for key in self._bind_mounts)
        if self._volumes:
            chmod_commands += ' && ' + ' && '.join(f"chmod +x {key}" for key in self._volumes)

        # Define the content of the script
        script_content = f'''\
        #!/bin/bash
        {command_str}
        '''

        run_command = (f'docker run {resources_str} {workdir_str} {env_str} '
                        f'{volumes_str} {bind_mounts_str} {docker_image} '
                        f'sh -c "{chmod_commands} && /tmp/{self._job_id}/run_script_{i}.sh"')

        self.reset()
        return run_command, script_content

def docker_run_command(executor: TesTaskExecutor, job_id: str, resource_conf: dict, volume_confs: List[dict],
                       input_confs: List[dict], output_confs: List[dict], inputs_directory: str, i: int) -> Tuple[str, str]:
    command_builder = DockerRunCommandBuilder()\
        .with_job_id(job_id) \
        .with_image(executor.image) \
        .with_command(
            list(map(lambda x: str(x), executor.command)),
            maybe_of(executor.stdin).map(lambda x: str(x)),
            maybe_of(executor.stdout).map(lambda x: str(x)),
            maybe_of(executor.stderr).map(lambda x: str(x))) \
        .with_workdir(executor.workdir) \
        .with_resource(resource_conf)

    if executor.env:
        [command_builder.with_env(env_name, env_value)
         for env_name, env_value in executor.env.items()]

    [command_builder.with_volume(volume_conf['container_path'], volume_conf['volume_name'])
     for volume_conf in volume_confs]
    [command_builder.with_bind_mount(input_conf['container_path'], input_conf['pulsar_path'])
     for input_conf in input_confs]

    return command_builder.get_run_command_script(inputs_directory, i)

def docker_stage_in_command(
    executor: TesTaskExecutor,
    resource_conf: dict,
    bind_mount: str,
    input_confs: List[dict]
) -> str:
    command_builder = (
        DockerRunCommandBuilder()
        .with_image(executor.image)
        .with_workdir(executor.workdir)
        .with_resource(resource_conf)
    )

    stage_in_commands = []

    for input_conf in input_confs:
        url = input_conf.get('url')
        input_type = input_conf.get('type', TesTaskIOType.FILE)
        pulsar_path = os.path.basename(input_conf['pulsar_path'])

        if not url:
            continue

        scheme = urlparse(url).scheme

        if input_type == TesTaskIOType.DIRECTORY:
            if scheme in ('http', 'https', 'ftp'):
                url_quoted = shlex.quote(url)
                cmd = (
                    f"wget --mirror --no-parent --no-host-directories "
                    f"--directory-prefix={pulsar_path} '{url_quoted}'"
                )
            else:
                raise ValueError(f"Unsupported scheme for directory input: {scheme}")
        else:
            cmd = f"curl -o {pulsar_path} '{url}'"

        stage_in_commands.append(cmd)

    if stage_in_commands:
        full_command = " && ".join(stage_in_commands)
        command_builder._command = Just(f'sh -c "{full_command}"')

    command_builder.with_bind_mount(executor.workdir, bind_mount)

    if executor.env:
        for env_name, env_value in executor.env.items():
            command_builder.with_env(env_name, env_value)

    return command_builder.get_run_command()

def docker_stage_out_command(
    executor: TesTaskExecutor,
    resource_conf: dict,
    output_confs: List[dict],
    volume_confs: List[dict]
) -> str:
    command_builder = (
        DockerRunCommandBuilder()
        .with_image(executor.image)
        .with_workdir(executor.workdir)
        .with_resource(resource_conf)
    )
    stage_out_commands = []

    for output in output_confs:
        path = output['container_path']
        url = output['url']
        output_type = output.get('type', TesTaskIOType.FILE)

        if output_type == TesTaskIOType.DIRECTORY:
            # bash find + curl for recursive upload inside container
            cmd = (
                f"base={shlex.quote(path)}; "
                f"url={shlex.quote(url)}; "
                f"find \"$base\" -type f -exec sh -c '"
                f"for filepath do "
                f"relpath=\"${{filepath#$base/}}\"; "
                f"curl -X POST -F \"file=@${{filepath}}\" -F \"path=${{relpath}}\" \"$url\"; "
                f"done' sh {{}} +"
            )
            stage_out_commands.append(cmd)
        else:
            safe_path = shlex.quote(path)
            safe_url = shlex.quote(url)
            cmd = f"curl -X POST -H 'Content-Type: multipart/form-data' -F 'file=@{safe_path}' {safe_url}"
            stage_out_commands.append(cmd)

    if stage_out_commands:
        full_command = " && ".join(stage_out_commands)
        command_builder._command = Just(f"sh -c {shlex.quote(full_command)}")

    for volume_conf in volume_confs:
        command_builder.with_volume(volume_conf['container_path'], volume_conf['volume_name'])

    if executor.env:
        for env_name, env_value in executor.env.items():
            command_builder.with_env(env_name, env_value)

    return command_builder.get_run_command()

def map_volumes(job_id: str, volumes: List[str], outputs: List[TesTaskOutput]):
    output_confs: List[dict] = []
    volume_confs: List[dict] = []

    existing_volume_paths = []

    # Process outputs
    for output in outputs:
        output_dirname = os.path.dirname(output.path)
        volume_name = f"vol-{job_id}-{output_dirname.replace('/', '')}"

        if output_dirname not in existing_volume_paths:
            volume_confs.append({
                'volume_name': volume_name,
                'container_path': output_dirname
            })
            existing_volume_paths.append(output_dirname)

        output_confs.append({
            'container_path': output.path,
            'url': output.url,
            'volume_name': volume_name
        })

    for v in volumes:
        if str(v) not in existing_volume_paths:
            volume_confs.append({
                'volume_name': f"vol-{job_id}-{str(v).replace('/', '')}",
                'container_path': str(v)
            })

    return output_confs, volume_confs

