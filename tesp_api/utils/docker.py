from typing import Dict, List

from pymonad.maybe import Nothing, Maybe, Just

from tesp_api.repository.model.task import TesTaskExecutor
from tesp_api.utils.functional import get_else_throw, maybe_of


class DockerRunCommandBuilder:

    def __init__(self) -> None:
        self._resource_cpu: Maybe[str] = Nothing
        self._resource_mem: Maybe[str] = Nothing
        self._docker_image: Maybe[str] = Nothing
        self._volumes: Dict[str, str] = {}
        self._command: Maybe[str] = Nothing

    def with_resource(self, resources: dict):
        if not resources: return self
        self._resource_cpu = maybe_of(resources["cpu_cores"])
        self._resource_mem = maybe_of(resources["ram_gb"])
        return self

    def with_volume(self, host_path: str, container_path: str):
        self._volumes[host_path] = container_path
        return self

    def with_image(self, docker_image: str):
        self._docker_image = Just(docker_image)
        return self

    def with_command(self, command: List[str], stdin: Maybe[str] = Nothing,
                     stdout: Maybe[str] = Nothing, stderr: Maybe[str] = Nothing):
        command_str = " ".join(command)
        self._command = Just(command_str) if command_str else Nothing
        self._command = self._command.map(lambda _command:
                                          f'sh -c "{_command}'
                                          f'{stdin.maybe("", lambda x: " <" + x)}'
                                          f'{stdout.maybe("", lambda x: " 1>" + x)}'
                                          f'{stderr.maybe("", lambda x: " 2>" + x)}"')
        return self

    def reset(self) -> None:
        self._resource_cpu = Nothing
        self._resource_mem = Nothing
        self._docker_image = Nothing
        self._volumes = {}
        return self

    def get_run_command(self) -> str:
        resources_str = (f' '
                         f'{self._resource_cpu.maybe("", lambda cpu: " --cpus="+str(cpu))}'
                         f'{self._resource_mem.maybe("", lambda mem: " --memory="+str(mem)+"g")}'
                         f' ')
        volumes_str = " ".join(map(lambda v_paths: f'-v {v_paths[0]}:{v_paths[1]}', self._volumes.items()))
        docker_image = get_else_throw(self._docker_image, ValueError('Docker image is not set'))
        command_str = self._command.maybe("", lambda x: x)
        run_command = f'docker run {resources_str} {volumes_str} {docker_image} {command_str}'
        self.reset()
        return run_command


def docker_run_command(executor: TesTaskExecutor, resource_conf: dict, input_confs: List[dict], output_confs: List[dict]) -> str:
    command_builder = DockerRunCommandBuilder()\
        .with_image(executor.image) \
        .with_command(
            list(map(lambda x: str(x), executor.command)),
            maybe_of(executor.stdin).map(lambda x: str(x)),
            maybe_of(executor.stdout).map(lambda x: str(x)),
            maybe_of(executor.stderr).map(lambda x: str(x))) \
        .with_resource(resource_conf)
    [command_builder.with_volume(input_conf['pulsar_path'], input_conf['container_path'])
     for input_conf in input_confs]
    [command_builder.with_volume(output_conf['pulsar_path'], output_conf['container_path'])
     for output_conf in output_confs]
    return command_builder.get_run_command()
