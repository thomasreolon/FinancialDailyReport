cache = []


def log(message: str):
    cache.append(message)
    print(message)
    
def log_error(message: str):
    log(f'\n<error>\n{message}\n</error>\n')
    
def log_warning(message: str):
    log(f'\n<warning>\n{message}\n</warning>\n')
    
def log_info(message: str):
    log(f'\n<info>\n{message}\n</info>\n')
    
def log_debug(message: str):
    log(f'\n<debug>\n{message}\n</debug>\n')