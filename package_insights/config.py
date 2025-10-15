def get_config(api_domain="api.cloudsmith.io", npm_domain="npm.cloudsmith.io", 
               python_domain="python.cloudsmith.io", docker_domain="docker.cloudsmith.io", 
               download_domain="dl.cloudsmith.io"):

    """
        This will help enforce some structure on our config. There might be a cleaner way 
        to do this per environment in future. 
    """
    
    return {
        "CLOUDSMITH_API_ROOT": api_domain,
        "CLOUDSMITH_DOCKER_ROOT": docker_domain,        
        "CLOUDSMITH_DOWNLOAD_ROOT": download_domain,
        "CLOUDSMITH_NPM_ROOT": npm_domain,
        "CLOUDSMITH_PYTHON_ROOT": python_domain,
    }

