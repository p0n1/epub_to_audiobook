import logging

def red_log_file(log_file):
    try:
        with open(log_file, "r") as log_file:
            return log_file.read()
    except FileNotFoundError:
        return f"Log file {log_file} not found."


def get_formatter(is_worker):
    if is_worker:
        return logging.Formatter(
            "%(asctime)s - [Worker-%(process)d] - %(filename)s:%(lineno)d - %(funcName)s - %(levelname)s - %(message)s"
        )
    else:
        return logging.Formatter(
            "%(asctime)s - %(filename)s:%(lineno)d - %(funcName)s - %(levelname)s - %(message)s"
        )

def setup_logging(log_level, log_file=None, is_worker=False):
    formatter = get_formatter(is_worker)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
