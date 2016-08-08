# -*- coding: utf-8 -*-
""" Scriptabit: Python scripting for Habitica.
"""

# Ensure backwards compatibility with Python 2
from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals)
from builtins import *

import logging
import logging.config
import os
from pkg_resources import Requirement, resource_filename
from yapsy.PluginManager import PluginManager

from .authentication import load_authentication_credentials
from .configuration import (
    get_configuration,
    get_config_file,
    copy_default_config_to_user_directory)
from .errors import ServerUnreachableError
from .habitica_service import HabiticaService
from .metadata import __version__
from .utility_functions import UtilityFunctions


def __init_logging(logging_config_file):
    """
    Initialises logging.

    Args:
        logging_config_file (str): The logging configuration file.
        """

    # Make sure the user copy of the logging config file exists
    copy_default_config_to_user_directory(logging_config_file, clobber=False)

    # Load the config
    logging.config.fileConfig(get_config_file(logging_config_file))
    logging.getLogger(__name__).debug('Logging online')

def __get_configuration():
    """ Builds and parses the hierarchical configuration from environment
variables, configuration files, command-line arguments, and argument defaults.

    Returns: The argparse compatible configuration object.
    """

    extra_args = [UtilityFunctions.get_arg_parser()]
    # TODO: Give all plugins a chance to extend the command line args.
    config, _ = get_configuration(parents=extra_args)

    return config

def __get_plugin_manager():
    """ Discovers and instantiates all plugins, returning a management object.

    Returns: yapsy.PluginManager: The plugin manager with the loaded plugins.
    """

    # Build the manager
    plugin_manager = PluginManager()

    # Build the location of the plugins that ship with scriptabit
    package_plugin_path = resource_filename(
        Requirement.parse("scriptabit"),
        os.path.join('scriptabit', 'plugins'))
    logging.getLogger(__name__).debug(
        'Loading package plugins from %s',
        package_plugin_path)

    # TODO: define and scan a user plugin directory
    plugin_manager.setPluginPlaces([package_plugin_path])

    # Load all plugins
    plugin_manager.collectPlugins()

    # Activate all loaded plugins
    # TODO: do I need to do this?
    for plugin_info in plugin_manager.getAllPlugins():
        plugin_manager.activatePluginByName(plugin_info.name)

    return plugin_manager

def __list_plugins(plugin_manager):
    """ Lists the available plugins.

    Args:
        plugin_manager (yapsy.PluginManager): the plugin manager containing
            the plugins.
    """

    for plugin_info in plugin_manager.getAllPlugins():
        logging.getLogger(__name__).info('\tPlugin: %s', plugin_info.name)

def start_cli():
    """ Command-line entry point for scriptabit """

    plugin_manager = __get_plugin_manager()
    config = __get_configuration()
    __init_logging(config.logging_config)
    logging.getLogger(__name__).info('scriptabit version %s', __version__)

    # Disabling the broad exception warning as catching
    # everything is *exactly* the intent here.
    # pylint: disable=broad-except
    try:
        if config.list_scenarios:
            logging.getLogger(__name__).debug('Listing available scenarios')
            __list_plugins(plugin_manager)
        else:
            # --------------------------------------------------
            # Running against Habitica.
            # Get everything warmed up and online.
            # --------------------------------------------------

            # user credentials
            auth_tokens = load_authentication_credentials(
                section=config.auth_section)

            # Habitica Service
            habitica_service = HabiticaService(
                auth_tokens,
                config.habitica_api_url)

            # Test for server availability
            if not habitica_service.is_server_up():
                raise ServerUnreachableError(
                    "Habitica API at '{0}' is unreachable or down".format(
                        config.habitica_api_url))

            logging.getLogger(__name__).info("Habitica API at '%s' is up",
                                             config.habitica_api_url)

            # Utility functions
            utility = UtilityFunctions(config, habitica_service)
            utility.run()

            if config.scenario:
                # Time to run the selected scenario
                logging.getLogger(__name__).debug(
                    "Running '%s' scenario", config.scenario)

                # TODO: scenario factory and execution
    except Exception as exception:
        logging.getLogger(__name__).error(exception, exc_info=True)
        # pylint: enable=broad-except

    logging.getLogger(__name__).info("Exiting")


if __name__ == 'main':
    start_cli()
