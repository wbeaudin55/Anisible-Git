#!/usr/bin/python
# -*- coding: utf-8 -*-

# ------------------------------------------------------------------------------
# Copyright (c) 2020, One Identity LLC
# File: client_sw_pkg_dir.py
# Desc: Ansible module for client_sw role that checks package install directory
#       for packages for the specified system, distribution, and architecture.
# Auth: Mark Stillings
# Note: 
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Required Ansible documentation
# ------------------------------------------------------------------------------

ANSIBLE_METADATA = {
    'metadata_version': '0.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = """ 
---
module: client_sw_pkg_dir 

short_description: Checks and parses Authentication Services client software install directory 

version_added: '2.9'

description: >
    Checks and parses Authentication Services client software install directory to find list
    of client software packages per the provided system (sys), distribution (dist), 
    architecture (arch), at the specified path (path) 

options:
    sys:
        description:
            - System (Linux, FreeBSD, Solaris, etc.)
        required: true
    dist:
        description:
            - Distribution (Redhat, Debian, etc.)
        required: true 
    arch:
        description:
            - Architecture (x86, amd64, etc.)
        required: true
    path:
        description:
            - Client software directory
        required: true

author:
    - Mark Stillings (mark.stillings@oneidentity.com)
"""

EXAMPLES = """
- name: Normal usage
  client_sw_pkg_dir:
    sys: linux  
    dist: debian 
    arch: amd64
    path: /var/tmp/authentication_services/client
  register: sw_dir_pkgs 
"""

RETURN = """ 
params:
    description: Parameters passed in
    type: dict
    returned: always
packages:
    description: The discovered packages and versions in supplied path
    type: dict
    returned: always
"""


# ------------------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------------------

from ansible.module_utils.basic import AnsibleModule
import os
import glob
import re


# ------------------------------------------------------------------------------
# Constants 
# ------------------------------------------------------------------------------

# Package paths for all supported systems and architectures 
PKG_PATHS = {
    'linux': {
        'i386': 'linux-x86',
        'x86_64': 'linux-x86_64',
        'amd64': 'linux-x86_64',
        'ppc64': 'linux-ppc64', 
        'ppc64le': 'linux-ppc64le', 
        'aarch64': 'linux-aarch64',
        'ia64': 'linux-ia64',
        's390': 'linux-s390',
        's390x': 'linux-s390x' 
    },  
    'freebsd': {
        'x86_64': 'freebsd-x86_64',
        'amd64': 'freebsd-x86_64' 
    },
    'sunos': {
        'i386': 'solaris10-x64',
        'x86_64': 'solaris10-x64',
        'amd64': 'solaris10-x64',
        'sparc': 'solaris10-sparc', 
        'sparc64': 'solaris10-sparc' 
    },
    'darwin': {
        'x86_64': 'macos-1012'
    },
    'hp-ux': {
        '9000/800': 'hpux-pa-11v3',
        'ia64': 'hpux-ia64' 
    } 
}

# Package file extensions for all supported distributions
PKG_EXTENSIONS = {
    'debian': 'deb',
    'ubuntu': 'deb',
    'redhat': 'rpm',
    'centos': 'rpm',
    'suse': 'rpm',
    'freebsd': 'txz',
    'solaris': 'pkg',
    'darwin': 'dmg',
    'hp-ux': 'depot' 
}


# ------------------------------------------------------------------------------
# Functions
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
def run_module():
    """
    Main Ansible module function
    """

    # Module argument info
    module_args = \
    {
        'sys': \
        {
            'type': 'str',
            'required': True
        },
        'dist': \
        {
            'type': 'str',
            'required': False 
        },
        'arch': \
        {
            'type': 'str',
            'required': True
        },
        'path': \
        {
            'type': 'str',
            'required': True
        } 
    }

    # Seed result value 
    result = \
    {
        'changed': False,
        'params': {},
        'packages': {},
        'ansible_facts': {} 
    }

    # Lean on boilerplate code in AnsibleModule class
    module = AnsibleModule(
        argument_spec = module_args,
        supports_check_mode = True
    )

    # Run logic
    # NOTE: This module makes no changes so check mode doesn't need to be handled
    #       specially 
    err, result = run_normal(module.params, result)

    # Exit - fail 
    if err:
        module.fail_json(msg = err, **result)

    # Exit - success
    module.exit_json(**result)

# ------------------------------------------------------------------------------
def run_normal(params, result):
    """
    Normal mode logic.

    params contains input parameters.

    result contains run results skeleton, will modify/add to and then return 
    this value along with an err value that contains None if no error or a string 
    describing the error.
    """

    # Return data 
    err = None 
    packages = {}

    # Parameters 
    path = params['path']
    sys = params['sys'].lower()
    dist = params['dist'].lower()
    arch = params['arch'].lower()

    # Check directory
    err = check_dir(path)

    # Find packages
    if err is None:
        err, packages = find_packages(path, sys, dist, arch)

    # Build result 
    result['params'] = params 
    result['packages'] = packages 
    result['ansible_facts'] = \
    {
        'qas': \
        {
            'packages': packages
        }
    }

    # Check for no packages found
    if not packages:
        err = 'no packages found'

    # Return
    return err, result

# ------------------------------------------------------------------------------
def check_dir(path):
    """
    Check if software source directory exists
    """

    # Return value
    err = None 

    # Check directory
    exists = os.path.exists(path)
    isdir = os.path.isdir(path)

    # Path does not exist
    if not exists:
        err = path + ' does not exist' 

    # Path is a file
    elif not isdir:    
        err = path + ' is a file not a directory' 

    # Return
    return err 

# ------------------------------------------------------------------------------
def find_packages(sw_path, sys, dist, arch):
    """
    Find packages
    """

    # Return values
    err = None 
    packages = {}

    # Find package path for specified sys and arch
    err, pkgs_dir = find_packages_path(sys, arch)

    # Get package extension for distribution 
    if not err:
        err, pkgs_ext = find_packages_ext(dist)

    # Find packages 
    if not err:
        pkgs_path = sw_path + '/' + pkgs_dir
        err, packages = parse_packages(pkgs_path, pkgs_ext) 
    
    # NOTE: Authentication Services macOS packages are grouped into dmg files, 
    #       so need to do some post-processing 
    if not err and sys == 'darwin':
        err, packages = process_macos_packages(packages)
    
    # Return
    return err, packages 

# ------------------------------------------------------------------------------
def find_packages_path(sys, arch):
    """
    Find package path for specified sys and arch
    """

    # Return values
    err = None 
    path = ''

    # Find path info
    if sys in PKG_PATHS:
        sys_archs = PKG_PATHS[sys]

        if arch in sys_archs:
            path = sys_archs[arch] 

        else:
            err = 'Unsupported architecture ' + arch 

    else:
        err = 'Unsupported system ' + sys 

    return err, path 

# ------------------------------------------------------------------------------
def find_packages_ext(dist):
    """
    find package file extension for specified OS distribution
    """

    # Return values
    err = None
    ext = ''

    # Find extension info
    if dist in PKG_EXTENSIONS:
        ext = PKG_EXTENSIONS[dist]

    else:
        err = 'Unsupported distribution ' + dist

    return err, ext

# ------------------------------------------------------------------------------
def parse_packages(path, ext):
    """
    Parse packages
    """

    # Return values
    err = None
    packages = {} 

    # regex strings
    pkg_name_re_str = '^[a-z]+'
    pkg_vers_re_str = '(?=.*)[\d]+\.[\d]+\.[\d]+[\.-][\d]+'

    # Compile regex's
    pkg_name_re = re.compile(pkg_name_re_str, re.I)
    pkg_vers_re = re.compile(pkg_vers_re_str)

    # Glob the package directory to find packages with correct file extension
    pkgs_str = path + '/*.' + ext
    pkgs = glob.glob(pkgs_str) 

    # Parse each package 
    for pkg in pkgs:
        
        pkg_path = pkg
        pkg_file = os.path.basename(pkg_path)

        pkg_name = None
        pkg_name_match = pkg_name_re.search(pkg_file)
        if pkg_name_match:
            pkg_name = pkg_name_match.group().lower()

        pkg_vers = '' 
        pkg_vers_match = pkg_vers_re.search(pkg_file)
        if pkg_vers_match:
            pkg_vers = pkg_vers_match.group()
            pkg_vers = pkg_vers.replace('-', '.')

        if pkg_name:
            packages[pkg_name] = \
            {
                'path': pkg_path,
                'file': pkg_file, 
                'vers': pkg_vers  
            }

    return err, packages

# ------------------------------------------------------------------------------
def process_macos_packages(dmg_pkgs):
    """
    Process macOS packages
    """

    # Return values
    err = None
    packages = {} 

    # macOS dmg prefixes
    vas_dmg_pkg = 'vas'
    vassite_dmg_pkg = 'vassite'
    ddns_dmg_pkg = 'dnsupdate'

    # macOS packages
    vas_pkgs = ['vasclnt', 'vasgp']
    vassite_pkgs = ['vasclnts', 'vasgps']
    common_pkgs = ['vassc', 'vascert', 'vasdev']
    ddns_pkgs = ['dnsupdate']

    # Check for VAS-*.dmg package
    vas_packages = process_dmg_package(dmg_pkgs, vas_dmg_pkg, vas_pkgs + common_pkgs + ddns_pkgs)

    # Check for VASsite*.dmg package
    vassite_packages = process_dmg_package(dmg_pkgs, vassite_dmg_pkg, vassite_pkgs + common_pkgs + ddns_pkgs)

    # Check for dnsupdate*.dmg package
    ddns_packages = process_dmg_package(dmg_pkgs, ddns_dmg_pkg, ddns_pkgs)

    # Merge found packages (order matters here, lowest priority first, highest priority last)
    packages.update(ddns_packages)
    packages.update(vassite_packages)
    packages.update(vas_packages)

    # Check for no packages found
    if not packages:
        err = 'no packages found'

    return err, packages

# ------------------------------------------------------------------------------
def process_dmg_package(dmg_pkgs, dmg_pkg, pkg_names):
    """
    Process macOS dmg package
    """

    packages = {}

    dmg_name = None
    dmg_data = None

    for key, val in dmg_pkgs.items():
        if key == dmg_pkg:
            dmg_name = key
            dmg_data = val

    if dmg_name:
        for pkg_name in pkg_names:
            packages[pkg_name] = \
            {
                'path': dmg_data['path'],
                'file': dmg_data['file'], 
                'vers': dmg_data['vers']  
            }

    return packages

# ------------------------------------------------------------------------------
def main():
    """
    Main
    """

    run_module()

# When run from command line
# ------------------------------------------------------------------------------
if __name__ == '__main__':
    main()