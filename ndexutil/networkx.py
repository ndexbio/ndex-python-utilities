# -*- coding: utf-8 -*-

import os
import logging
import tempfile
import ndexutil
import shutil
import json
from ndexutil.argparseutil import ArgParseFormatter
from ndexutil.config import NDExUtilConfig
from ndexutil.ndex import NDExExtraUtils
from ndexutil.exceptions import NDExUtilError
from ndex2.client import Ndex2
from ndex2.nice_cx_network import DefaultNetworkXFactory
import ndex2
import networkx
from requests.exceptions import HTTPError

# create logger
logger = logging.getLogger('ndexutil.networkx')


SPRING_LAYOUT = 'spring'
"""
Spring layout
"""

CIRCULAR_LAYOUT = 'circular'
"""
Circular layout
"""

KAMADA_KAWAI_LAYOUT = 'kamada_kawai'
"""
Kamada Kawai layout
"""

PLANAR_LAYOUT = 'planar'
"""
Planar layout
"""

SHELL_LAYOUT = 'shell'
"""
Shell layout
"""

SPECTRAL_LAYOUT = 'spectral'
"""
Spectral layout
"""

SPIRAL_LAYOUT = 'spiral'
"""
Spiral layout
"""


class NetworkxLayoutWrapper(object):
    """
    Wrapper for networkx layout algorithms
    """
    def __init__(self):
        """
        Constructor
        """
        pass

    def spring_layout(self, g, k=None, pos=None, fixed=None,
                      iterations=50, threshold=0.0001,
                      weight='weight', scale=1,
                      center=None, dim=2, seed=None):
        """
        Applies networkx spring layout on graph
        See :py:class:`networkx.drawling.layout.spring_layout` for usage

        :return: positions for nodes generated by layout algorithm
        :rtype: dict
        """
        return networkx.drawing.spring_layout(g,
                                              k=k, pos=pos, fixed=fixed,
                                              iterations=iterations,
                                              threshold=threshold,
                                              weight=weight, scale=scale,
                                              center=center, dim=dim, seed=seed)

    def convert_positions_to_cartesian_aspect(self, networkx_pos=None):
        """
        Converts node coordinates from a pos object
        to a list of dicts with following format:
        [{'node': <node id>,
          'x': <x position>,
          'y': <y position>}]

        :param networkx_pos: dict of node coordinates from networkx layout
                             algorithm. Which should be in format of:
                             {NODEID: [X, Y],...}
        :type networkx_pos: dict
        :return: coordinates as list of dict objects in format:
                 [{'node': ID,'x': X,'y': Y}...
        :rtype: list
        """
        if networkx_pos is None:
            raise NDExUtilError('networkx_pos is None')

        return [{'node': n,
                 'x': float(networkx_pos[n][0]),
                 'y': float(networkx_pos[n][1])} for n in networkx_pos]


class NetworkxLayoutCommand(object):
    """
    Updates network in NDEx with Networkx layout
    """
    COMMAND = 'networkxlayout'

    def __init__(self, theargs,
                 layout_wrapper=NetworkxLayoutWrapper(),
                 ndexextra=NDExExtraUtils(),
                 altclient=None):
        """
        Constructor

        :param theargs: command line arguments from Argparse
                        ie theargs.name theargs.type
        """
        self._args = theargs
        self._user = self._args.username
        self._pass = self._args.password
        self._server = self._args.server
        self._tmpdir = None  # set in run() function
        self._layoutwrapper = layout_wrapper
        self._ndexextra = ndexextra
        self._altclient = altclient

    def _parse_config(self):
        """
        Parses user, password, and server from command line
        positional flags unless those values are '-' in which
        case those values are extracted from config
        specified by --profile flag

        If --profile is used then these values are extracted
        from config:

        :py:const:`~ndexutil.config.NDExUtilConfig.USER`
        :py:const:`~ndexutil.config.NDExUtilConfig.PASSWORD`
        :py:const:`~ndexutil.config.NDExUtilConfig.SERVER`

        :return: None
        """
        if self._user != '-' and self._pass != '-' and self._server != '-':
            return

        ncon = NDExUtilConfig(conf_file=self._args.conf)
        con = ncon.get_config()
        if self._user == '-':
            self._user = con.get(self._args.profile, NDExUtilConfig.USER)

        if self._pass == '-':
            self._pass = con.get(self._args.profile, NDExUtilConfig.PASSWORD)

        if self._server == '-':
            self._server = con.get(self._args.profile, NDExUtilConfig.SERVER)

    def _get_client(self):
        """
        Gets Ndex2 client by parsing command line flags or extracting
        values from --profile flag

        :return: Ndex2 python client
        :rtype: :py:class:`~ndex2.client.Ndex2`
        """
        if self._altclient is not None:
            return self._altclient
        return Ndex2(self._server, self._user, self._pass)

    def run(self):
        """
        Retrieves network specified by --uuid, applies layout
        specified via --layout flag and optionally updates layout
        or entire network on NDEx

        :raises NDExUtilError if there is an error
        :return: 0 upon success otherwise failure
        """

        logger.warning('THIS IS AN UNTESTED ALPHA IMPLEMENTATION '
                       'AND MAY CONTAIN ERRORS')

        self._parse_config()
        client = self._get_client()
        self._tmpdir = tempfile.mkdtemp(prefix=self._args.tmpdir)
        try:
            input_cx_file = os.path.join(self._tmpdir, self._args.uuid + '.cx')
            self._ndexextra.download_network_from_ndex(client=client,
                                                       networkid=self._args.uuid,
                                                       destfile=input_cx_file)

            aspect_data, output_cx_file = self.apply_layout(cxfile=input_cx_file)

            if self._args.skipupload is True:
                logger.info('Skipping upload to NDEx')
                return 0

            if self._args.updatefullnetwork is True:
                logger.info('Updating entire network with id: ' +
                            str(self._args.uuid) + ' on NDEx server: ' +
                            str(self._server) +
                            ' since --updatenetwork flag is set')
                self._ndexextra.update_network_on_ndex(client=client,
                                                       networkid=self._args.uuid,
                                                       cxfile=output_cx_file)
            else:
                self._ndexextra.update_aspect_on_ndex(client=client,
                                                      networkid=self._args.uuid,
                                                      aspect_name='cartesianLayout',
                                                      aspect_data=aspect_data)
            return 0
        except HTTPError as he:
            logger.fatal('Received error code: ' +
                         str(he.response.status_code) +
                         ' from NDEx server', he)
            if 'message' in he.response.json():
                logger.fatal('Message from NDEx server: ' + str(he.response.json()['message']))
            return 1
        finally:
            shutil.rmtree(self._tmpdir)

    def get_center_as_list(self):
        """
        Parses string passed into --center that should be
        coordinates with comma delimiter (example: X,Y),
        this method returns a list of each element

        :return: list of x,y coordinate of center or `None` if value is `None`
        :rtype: list
        """
        if self._args.center is None:
            return None

        return self._args.center.split(',')

    def _run_layout_algorithm(self, netx_graph=None):
        """
        Runs layout specified by <layout> command line flag
        on network `netx_graph`

        :param netx_graph: Network to run the layout on
        :type netx_graph: :py:class:`~networkx.Graph`
        :return: positions generated by layout algorithm
        :rtype: dict
        """
        center_val = self.get_center_as_list()
        if self._args.layout == SPRING_LAYOUT:
            return self._layoutwrapper.spring_layout(netx_graph,
                                                     k=self._args.spring_k,
                                                     iterations=self._args.spring_iterations,
                                                     center=center_val,
                                                     scale=self._args.scale)

        raise NDExUtilError(self(self._args.layout) +
                            ' does not match supported layout')

    def apply_layout(self, cxfile=None):
        """
        Apply layout via networkx on network specified by
        cxfile

        :param cxfile: Path to CX file of network to generate layout for
        :type cxfile: str
        :return: (cartesianLayout aspect, path to CX file with layout)
        :rtype: tuple
        """

        logger.info('Loading network')
        net = ndex2.create_nice_cx_from_file(cxfile)
        netx_fac = DefaultNetworkXFactory()
        netx_graph = netx_fac.get_graph(net)

        logger.info('Applying Networkx ' +
                    self._args.layout +
                    ' network on network')

        pos = self._run_layout_algorithm(netx_graph=netx_graph)

        del netx_graph

        logger.debug('Converting coordinates from networkx to CX format')
        cart_aspect = self._layoutwrapper.convert_positions_to_cartesian_aspect(pos)

        if self._args.outputcx is not None:
            output_cx_file = self._args.outputcx
        else:
            output_cx_file = os.path.join(self._tmpdir, 'output.cx')
        logger.info('Writing out CX file: ' + output_cx_file)
        net.set_opaque_aspect('cartesianLayout', cart_aspect)
        with open(output_cx_file, 'w') as f:
            json.dump(net.to_cx(), f)

        return cart_aspect, output_cx_file

    @staticmethod
    def add_subparser(subparsers):
        """
        adds a subparser
        :param subparsers:
        :return:
        """
        desc = """

Version {version}

The {cmd} command updates layout on a network in NDEx using Networkx.
The network must be specified by NDEx UUID via --uuid flag. 

The flags --scale and --center work for all layouts. Some flags
only are relevant for certain layouts. Those flags will start
with --<LAYOUT NAME>_<FLAG> like --spring_k and --spring_iterations
flags whic only work for spring layout.

Upon success script will exit with code 0 otherwise error.

Example:

ndexmisctools.py networkxlayout spring - - - --uuid XXXX-XXX --spring_k 0.5

WARNING: THIS IS AN UNTESTED ALPHA IMPLEMENTATION AND MAY CONTAIN
         ERRORS. YOU HAVE BEEN WARNED.

        """.format(version=ndexutil.__version__,
                   cmd=NetworkxLayoutCommand.COMMAND)

        parser = subparsers.add_parser(NetworkxLayoutCommand.COMMAND,
                                       help='Updates layout of network via '
                                            'Cytoscape',
                                       description=desc,
                                       formatter_class=ArgParseFormatter)
        parser.add_argument('layout', choices=[SPRING_LAYOUT],
                            help='Name of layout to run.')
        parser.add_argument('username', help='NDEx username, if set to - '
                                             'then value from config will '
                                             'be used')
        parser.add_argument('password', help='NDEx password, if set to - '
                                             'then value from config will '
                                             'be used')
        parser.add_argument('server', help='NDEx server, if set to - then '
                                           'value from config will be used,'
                                           'For production, use public.ndexbio.org')
        parser.add_argument('--uuid', required=True,
                            help='The UUID of network in NDEx to update')
        parser.add_argument('--scale', type=float, default=300.0,
                            help='Scale to pass to layout algorithm.')
        parser.add_argument('--center', type=str,
                            help='Comma delimited coordinate denoting '
                                 'center for layout. Should be in format '
                                 'of X,Y or Y,X not sure which way networkx'
                                 'does coordinates')
        parser.add_argument('--' + SPRING_LAYOUT + '_iterations', type=int,
                            default=50,
                            help='Maximum number of iterations taken ')
        parser.add_argument('--' + SPRING_LAYOUT + '_k', type=float,
                            help='Optimal distance between nodes. '
                                 'If unset the distance is set to 1/sqrt(n) '
                                 'where n is the number of nodes. Increase '
                                 'this value to move nodes farther apart.')
        parser.add_argument('--tmpdir',
                            help='Sets temp directory used for processing. If '
                                 'not set, then directory used is the '
                                 'default for Python\'s '
                                 'tempfile.mkdtemp() function')
        parser.add_argument('--skipupload', action='store_true',
                            help='If set, layout will NOT updated for '
                                 'network in NDEx')
        parser.add_argument('--outputcx',
                            help='If set, CX will be written to this file')
        parser.add_argument('--updatefullnetwork', action='store_true',
                            help='If set, update entire network instead '
                                 'of just the cartesianLayout aspect')
        return parser
