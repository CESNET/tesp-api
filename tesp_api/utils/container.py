import os
import re
import shlex
from urllib.parse import urlparse
from typing import Dict, List, Tuple, Optional, Union

from pymonad.maybe import Nothing, Maybe, Just

from tesp_api.repository.model.task import TesTaskExecutor, TesTaskOutput, TesTaskIOType
from tesp_api.utils.functional import get_else_throw, maybe_of

SHELL_PATTERN = re.compile(r"[|&;<>(){}$*?\"'\\]")

class ContainerCommandBuilder:
    def __init__(self, container_type: str) -> None:
        self.container_type = container_type
        self._job_id: str = ""
        self._resource_cpu: Maybe[str] = Nothing
        self._resource_mem: Maybe[str] = Nothing
        self._image: Maybe[str] = Nothing
        self._workdir: Maybe[str] = Nothing
        self._envs: Dict[str, str] = {}
        self._volumes: Dict[str, str] = {}
        self._bind_mounts: Dict[str, str] = {}
        self._dirs_to_create: List[str] = []
        self._command: Maybe[str] = Nothing
        self._stdin: Maybe[str] = Nothing
        self._stdout: Maybe[str] = Nothing
        self._stderr: Maybe[str] = Nothing

    def with_job_id(self, job_id: str):
        self._job_id = job_id
        return self

    def with_resource(self, resources: dict):
        if not resources:
            return self
        self._resource_cpu = maybe_of(resources.get("cpu_cores"))
        self._resource_mem = maybe_of(resources.get("ram_gb"))
        return self

    def with_bind_mount(self, container_path: str, host_path: str):
        self._bind_mounts[container_path] = host_path
        return self

    def with_volume(self, container_path: str, volume_name: str):
        self._volumes[container_path] = volume_name
        return self

    def with_directory(self, path: str):
        self._dirs_to_create.append(path)
        return self

    def with_image(self, image: str):
        if self.container_type == "singularity":
            # If it's an absolute path, use as-is
            if os.path.isabs(image):
                self._image = Just(image)
            # If it's already got a URI scheme, use as-is
            elif image.startswith(("docker://", "library://", "shub://", "oras://")):
                self._image = Just(image)
            # Otherwise, assume Docker Hub reference
            else:
                self._image = Just(f"docker://{image}")
        else:
            self._image = Just(image)
        return self

    def with_workdir(self, workdir: str):
        self._workdir = maybe_of(workdir)
        return self

    def with_env(self, name: str, value: str):
        self._envs[name] = value
        return self

    def with_command(self, command: List[str], stdin: Maybe[str] = Nothing,
                     stdout: Maybe[str] = Nothing, stderr: Maybe[str] = Nothing):
        self._stdin = stdin
        self._stdout = stdout
        self._stderr = stderr
        
        if not command:
            self._command = Nothing
            return self

        # Check if already wrapped in shell
        if self._is_shell_wrapped(command):
            self._command = Just(command)
            return self

        # Wrap in shell if needed
        if self.requires_shell(command) or self.container_type == "singularity":
            shell_cmd = " ".join(shlex.quote(str(arg)) for arg in command)
            shell_cmd = self._escape_redirections(
                shell_cmd,
                self._stdin,
                self._stdout,
                self._stderr
            )
            self._command = Just(["sh", "-c", shell_cmd])
        else:
            cmd = list(map(str, command))
            cmd = self._add_redirections(cmd)
            self._command = Just(cmd)
            
        return self

    def _is_shell_wrapped(self, command) -> bool:
        if isinstance(command, list):
            return len(command) >= 2 and command[0] == "sh" and command[1] == "-c"
        return False

    def requires_shell(self, command: List[str]) -> bool:
        return any(
            isinstance(arg, str) and SHELL_PATTERN.search(arg)
            for arg in command
        )

    def _escape_redirections(self, cmd: str, stdin, stdout, stderr) -> str:
        redirections = [
            ('<', stdin),
            ('>', stdout),
            ('2>', stderr),
        ]
        for op, val in redirections:
            if val and val != Nothing:
                path = val.maybe("", lambda x: x)
                if path:
                    cmd += f" {op} {shlex.quote(path)}"
        return cmd

    def _add_redirections(self, cmd: List[str]) -> List[str]:
        redirections = []
        if self._stdin != Nothing:
            path = self._stdin.maybe("", lambda x: x)
            if path:
                redirections.extend(["<", path])
        if self._stdout != Nothing:
            path = self._stdout.maybe("", lambda x: x)
            if path:
                redirections.extend([">", path])
        if self._stderr != Nothing:
            path = self._stderr.maybe("", lambda x: x)
            if path:
                redirections.extend(["2>", path])
        return cmd + redirections

    def reset(self) -> None:
        self._resource_cpu = Nothing
        self._resource_mem = Nothing
        self._image = Nothing
        self._workdir = Nothing
        self._envs = {}
        self._volumes = {}
        self._bind_mounts = {}
        self._dirs_to_create = []
        self._command = Nothing
        self._stdin = Nothing
        self._stdout = Nothing
        self._stderr = Nothing
        return self

    def get_run_command(self) -> str:
        # Common resource flags
        cpu_flag = self._resource_cpu.maybe("", lambda cpu:
        f"--cpus={cpu}" if self.container_type == "docker" else f"--cpu={cpu}")

        mem_flag = self._resource_mem.maybe("", lambda mem:
        f"--memory={mem}g" if self.container_type == "docker" else f"--memory={mem}G")

        # Environment variables
        env_flags = []
        for k, v in self._envs.items():
            if self.container_type == "docker":
                env_flags.append(f'-e {shlex.quote(k)}={shlex.quote(v)}')
            else:
                env_flags.append(f'--env {k}="{v}"')

        # Work directory
        workdir_flag = self._workdir.maybe("", lambda w:
        f'-w "{w}"' if self.container_type == "docker" else f'--pwd "{w}"')

        # Image
        image = self._image.maybe("", lambda i: i)

        # Mounts
        mount_flags = []
        mkdir_cmds = []  # for singularity pre-creation

        # Handle explicit directories (Singularity only)
        if self.container_type == "singularity":
            for path in self._dirs_to_create:
                mkdir_cmds.append(f'mkdir -p "{path}"')

        # Handle mounts
        if self.container_type == "docker":
            for container_path, host_path in self._bind_mounts.items():
                mount_flags.append(f'-v "{host_path}":"{container_path}"')
            for container_path, volume_name in self._volumes.items():
                mount_flags.append(f'-v "{volume_name}":"{container_path}"')
        else:  # singularity
            for container_path, host_path in self._bind_mounts.items():
                mount_flags.append(f'-B "{host_path}":"{container_path}"')
            for container_path, volume_name in self._volumes.items():
                # Volumes are always directories, so we can auto-create them
                mkdir_cmds.append(f'mkdir -p "{volume_name}"')
                mount_flags.append(f'-B "{volume_name}":"{container_path}"')

        # Command
        command_str = self._command.maybe("", lambda cmd:
        " ".join(shlex.quote(arg) for arg in cmd) if isinstance(cmd, list) else cmd)

        # Build final command
        if self.container_type == "docker":
            return (
                f"docker run {cpu_flag} {mem_flag} {workdir_flag} "
                f"{' '.join(env_flags)} {' '.join(mount_flags)} "
                f"{image} {command_str}"
            ).strip()
        else:  # singularity
            mkdir_prefix = " && ".join(mkdir_cmds)
            singularity_cmd = (
                f"singularity exec {cpu_flag} {mem_flag} {workdir_flag} "
                f"{' '.join(env_flags)} {' '.join(mount_flags)} "
                f"{image} {command_str}"
            ).strip()
            return f"{mkdir_prefix} && {singularity_cmd}" if mkdir_prefix else singularity_cmd


# Unified command functions
def stage_in_command(
    executor: TesTaskExecutor,
    resource_conf: dict,
    bind_mount: str,
    input_confs: List[dict],
    container_type: str
) -> str:
    builder = ContainerCommandBuilder(container_type) \
        .with_image(executor.image) \
        .with_workdir(executor.workdir) \
        .with_resource(resource_conf) \
        .with_directory(bind_mount)

    commands = []
    for input_conf in input_confs:
        url = input_conf.get('url')
        if not url:
            continue
            
        path = input_conf['pulsar_path']
        input_type = input_conf.get('type', TesTaskIOType.FILE)
        filename = os.path.basename(path)
        
        if input_type == TesTaskIOType.DIRECTORY:
            # Recursive download
            commands.append(
                f"wget -e robots=off --mirror --no-parent --no-host-directories "
                f"--directory-prefix={shlex.quote(filename)} {shlex.quote(url)}"
            )
        else:
            # Single file download
            commands.append(f"curl -f -o {shlex.quote(filename)} {shlex.quote(url)}")
    
    if commands:
        builder.with_command(["sh", "-c", " && ".join(commands)])

    builder.with_bind_mount(executor.workdir, bind_mount)
    
    if executor.env:
        for env_name, env_value in executor.env.items():
            builder.with_env(env_name, env_value)

    return builder.get_run_command()

def run_command(
    executor: TesTaskExecutor,
    job_id: str,
    resource_conf: dict,
    volume_confs: List[dict],
    input_confs: List[dict],
    output_confs: List[dict],
    inputs_directory: str,
    container_type: str,
    job_directory: Optional[str] = None,
    executor_index: int = 0
) -> str:
    builder = ContainerCommandBuilder(container_type) \
        .with_job_id(job_id) \
        .with_image(executor.image) \
        .with_command(
            list(map(str, executor.command)),
            maybe_of(executor.stdin).map(str),
            maybe_of(executor.stdout).map(str),
            maybe_of(executor.stderr).map(str)
        ) \
        .with_workdir(executor.workdir) \
        .with_resource(resource_conf)

    if executor.env:
        for env_name, env_value in executor.env.items():
            builder.with_env(env_name, env_value)

    # Handle volumes and bind mounts
    for volume_conf in volume_confs:
        builder.with_volume(volume_conf['container_path'], volume_conf['volume_name'])
    
    for input_conf in input_confs:
        if input_conf.get('type') == TesTaskIOType.DIRECTORY:
            builder.with_directory(input_conf['pulsar_path'])

        builder.with_bind_mount(input_conf['container_path'], input_conf['pulsar_path'])

    if not executor.workdir and container_type == "singularity":
        builder.with_workdir("/")

    return builder.get_run_command()

def stage_out_command(
    executor: TesTaskExecutor,
    resource_conf: dict,
    output_confs: List[dict],
    volume_confs: List[dict],
    container_type: str,
    bind_mount: Optional[str] = None,
    job_directory: Optional[str] = None
) -> str:
    builder = ContainerCommandBuilder(container_type) \
        .with_image(executor.image) \
        .with_workdir(executor.workdir) \
        .with_resource(resource_conf)

    commands = []
    for output in output_confs:
        path = output['container_path']
        url = output['url']
        output_type = output.get('type', TesTaskIOType.FILE)
        
        if output_type == TesTaskIOType.DIRECTORY:
            # Recursive upload
            cmd = (
                f"find {shlex.quote(path)} -type f -exec "
                f"curl -f -X POST -F 'file=@{{}}' {shlex.quote(url)} \\;"
            )
        else:
            # Single file upload
            cmd = f"curl -f -X POST -F 'file=@{shlex.quote(path)}' {shlex.quote(url)}"
        
        commands.append(cmd)
    
    if commands:
        builder.with_command(["sh", "-c", " && ".join(commands)])

    # Mount required directories
    if container_type == "singularity" and bind_mount:
        builder.with_bind_mount(executor.workdir, bind_mount)
        builder.with_directory(bind_mount)
    
    for volume_conf in volume_confs:
        builder.with_volume(volume_conf['container_path'], volume_conf['volume_name'])

    if executor.env:
        for env_name, env_value in executor.env.items():
            builder.with_env(env_name, env_value)

    return builder.get_run_command()

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
