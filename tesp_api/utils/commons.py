import os
import subprocess
import logging


class Commons:

    log = logging.getLogger(__name__)

    @classmethod
    def execute_script(cls, script_path, *script_parameters):
        script_and_parameters = [ script_path ] + list(script_parameters)
        cls.log.debug(f"calling script and parameters { script_and_parameters }")
        try:
            result = subprocess.run(script_and_parameters, check=True, text=True, capture_output=True)
            cls.log.debug(f"calling script and parameters completed with rc = { result.returncode }")
            return result.stdout
        except subprocess.CalledProcessError as e:
            cls.log.error(f"error occurred during execution of { script_and_parameters }, { e.stderr }", exc_info=True)
            raise e

    @classmethod
    def get_service_version(cls):
        this_module_path = os.path.abspath(__file__)
        this_module_dir = os.path.dirname(this_module_path)
        script_path = os.path.join(this_module_dir, "../../ci/version.sh")
        change_log_path = os.path.join(this_module_dir, "../../CHANGELOG.md")
        return cls.execute_script(script_path, change_log_path)
