import logging
from time import sleep
import docker

logger = logging.getLogger(__name__)


_client = None

def get_docker_client():
    try:
        global _client
        if not _client:
            _client = docker.from_env()
        return _client
    except Exception as e:
        logger.error(f"Failed to connect to Docker. Make sure its installed and running. Error: {e}")
        exit(1)

def get_container(name):
    containers = get_docker_client().containers.list(all=True, filters={"name": name})
    if containers and len(containers) > 0:
        if len(containers) > 1:
            raise RuntimeError(
                f"More than one container found with name {name}: {containers}"
            )
        if containers[0].status == 'running':
            return containers[0]

    logger.info(f"Container with {name} not found.")
    return None

def wait_until_initialised(container, log_keyword, time_out=30):
    counter = 0
    while counter < time_out:
        log = container.logs(tail=1).decode()
        if log_keyword in log:
            return
        logger.info("Waiting for container to be ready...")
        sleep(1)
        counter += 1

def remove_container(container):
    if container:
        container.remove(force=True)

def get_container_env_value(container, env_var):
    env = container.attrs['Config']['Env']
    for var in env:
        var_data = var.split("=")
        name = var_data[0]
        value = var_data[1]
        if name == env_var:
            return value
    return None

def is_env_var_equal(container, env_var_name, expected_value):
    envs = container.attrs['Config']['Env']
    for var in envs:
        if "=" in var:
            var_data = var.split("=")
            name = var_data[0]
            value = var_data[1]
            if name == env_var_name:
                if value == expected_value:
                    return True
                return False
    return False