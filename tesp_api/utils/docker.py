import os
import re
import shlex
from urllib.parse import urlparse
from typing import Dict, List, Tuple

from pymonad.maybe import Nothing, Maybe, Just

from tesp_api.repository.model.task import TesTaskExecutor, TesTaskOutput, TesTaskIOType
from tesp_api.utils.functional import get_else_throw, maybe_of

SHELL_PATTERN = re.compile(
    r"[|&;<>(){}$*?\"'\\`]"  # shell metacharacters
)

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

    def requires_shell(self, command: List[str]) -> bool:
        return any(
            isinstance(arg, str) and SHELL_PATTERN.search(arg)
            for arg in command
        )

    def escape_redirections(self, cmd: str, stdin=None, stdout=None, stderr=None) -> str:
        redirections = [
            ('<', stdin),
            ('>', stdout),
            ('2>', stderr),
        ]
        for op, val in redirections:
            if isinstance(val, Maybe):
                val = val.maybe(None, lambda x: None if str(x) == "Nothing" else x)
            elif str(val) == "Nothing":
                val = None
            if val:
                cmd += f" {op} {shlex.quote(val)}"
        return cmd

    def with_command(self, command: List[str], stdin=Nothing, stdout=Nothing, stderr=Nothing):
        if not command:
            self._command = Nothing
            return self

        if self.requires_shell(command):
            shell_cmd = " ".join(map(shlex.quote, map(str, command)))
            shell_cmd = self.escape_redirections(shell_cmd, stdin, stdout, stderr)
            self._command = Just(["sh", "-c", shell_cmd])
        else:
            # Only for direct commands, sanitize the redirections
            def maybe_path(val):
                if isinstance(val, Maybe):
                    return val.maybe(None, lambda x: None if str(x) == "Nothing" else x)
                return None if str(val) == "Nothing" else val

            stdin_val = maybe_path(stdin)
            stdout_val = maybe_path(stdout)
            stderr_val = maybe_path(stderr)

            cmd = list(map(str, command))
            redirs = [("<", stdin_val), (">", stdout_val), ("2>", stderr_val)]
            cmd += [part for op, val in redirs if val for part in (op, val)]
            self._command = Just(cmd)

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
        print("Constructing docker run command...")

        print("Before maybe(_resource_cpu)")
        cpu_flag = self._resource_cpu.maybe("", lambda cpu: f"--cpus={cpu}")
        print("After maybe(_resource_cpu)")

        print("Before maybe(_resource_mem)")
        mem_flag = self._resource_mem.maybe("", lambda mem: f"--memory={mem}")
        print("After maybe(_resource_mem)")

        print("Before maybe(_workdir)")
        workdir_str = self._workdir.maybe("", lambda w: f'-w="{w}"')
        print("After maybe(_workdir)")

        print("Before maybe(_docker_image)")
        image = self._docker_image.maybe("", lambda i: i)
        print("After maybe(_docker_image)")

        bind_mounts_str = " ".join(
            f'-v "{host}":"{container}"' for container, host in self._bind_mounts.items()
        )
        volumes_str = " ".join(
            f'-v "{host}":"{container}"' for container, host in self._volumes.items()
        )
        env_str = " ".join(
            f'-e {shlex.quote(k)}={shlex.quote(v)}' for k, v in self._envs.items()
        )

        def quote_command(cmd):
            print(f"quote_command called with: {cmd} (type: {type(cmd)})")
            if isinstance(cmd, str):
                return cmd
            if isinstance(cmd, list):
                return " ".join(shlex.quote(arg) for arg in cmd)
            return ""

        print("Before maybe(_command)")
        command_str = self._command.maybe("", quote_command)
        print("After maybe(_command)")

        full_command = f"docker run {cpu_flag} {mem_flag} {workdir_str} {env_str} {volumes_str} {bind_mounts_str} {image} {command_str}".strip()

        self.reset()
        return full_command

    def get_run_command_script(self, inputs_directory: str, i: int) -> Tuple[str, str]:
        resources_str = (f'{self._resource_cpu.maybe("", lambda cpu: " --cpus="+str(cpu))}'
                         f'{self._resource_mem.maybe("", lambda mem: " --memory="+str(mem)+"g")}')
        bind_mounts_str = " ".join(map(lambda v_paths: f'-v \"{v_paths[1]}\":\"{v_paths[0]}\"', self._bind_mounts.items()))
        volumes_str     = " ".join(map(lambda v_paths: f'-v \"{v_paths[1]}\":\"{v_paths[0]}\"', self._volumes.items()))
        docker_image    = get_else_throw(self._docker_image, ValueError('Docker image is not set'))
        workdir_str     = self._workdir.maybe("", lambda workdir: f"-w=\"{str(workdir)}\"")
        volumes_str    += f' -v "{inputs_directory}/run_script_{i}.sh":"/tmp/{self._job_id}/run_script_{i}.sh"'
        env_str         = " ".join(map(lambda env: f'-e {env[0]}=\"{env[1]}\"', self._envs.items()))
        command_str = maybe_of(self._command).maybe("", lambda x: " ".join(shlex.quote(arg) for arg in x))

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

    return command_builder.get_run_command() # _script(inputs_directory, i)

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
        print(f"Staging out: {path} -> {url} (type: {output_type})")

        if output_type == TesTaskIOType.DIRECTORY:
            # bash find + curl for recursive upload inside container
            cmd = (
                f"base={shlex.quote(path)}; "
                f"url={shlex.quote(url)}; "
                f"find \"$base\" -type f | while read -r filepath; do "
                f"relpath=\"${{filepath#$base/}}\"; "
                f"curl -X POST -F \"file=@${{filepath}};filename=${{relpath}}\" \"$url\"; "
                f"done"
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
            'volume_name': volume_name,
            'type': output.type
        })

    for v in volumes:
        if str(v) not in existing_volume_paths:
            volume_confs.append({
                'volume_name': f"vol-{job_id}-{str(v).replace('/', '')}",
                'container_path': str(v)
            })

    return output_confs, volume_confs

