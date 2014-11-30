from bootstrapvz.common.tools import log_check_call
import logging
log = logging.getLogger(__name__)


def pick_build_server(build_servers, preferences, manifest):
	# Validate the build servers list
	from bootstrapvz.common.tools import load_data
	import os.path
	schema = load_data(os.path.normpath(os.path.join(os.path.dirname(__file__), 'build-servers-schema.yml')))
	import jsonschema
	jsonschema.validate(build_servers, schema)

	if manifest.provider['name'] == 'ec2':
		must_bootstrap = 'ec2-' + manifest.volume['backing']
	else:
		must_bootstrap = manifest.provider['name']

	def matches(name, settings):
		if preferences.get('name', name) != name:
			return False
		if preferences.get('release', settings['release']) != settings['release']:
			return False
		if must_bootstrap not in settings['can_bootstrap']:
			return False
		return True

	for name, settings in build_servers.iteritems():
		if not matches(name, settings):
			continue
		if settings['type'] == 'local':
			return LocalBuildServer(settings)
		else:
			return RemoteBuildServer(settings)
	raise Exception('Unable to find a build server that matches your preferences.')


class BuildServer(object):

	def __init__(self, settings):
		self.settings = settings
		self.build_settings = settings.get('build_settings', {})
		self.can_bootstrap = settings['can_bootstrap']
		self.release = settings.get('release', None)


class LocalBuildServer(BuildServer):
	pass


class RemoteBuildServer(BuildServer):

	def __init__(self, settings):
		super(RemoteBuildServer, self).__init__(settings)
		self.address = settings['address']
		self.port = settings['port']
		self.username = settings['username']
		self.password = settings['password']
		self.root_password = settings['root_password']
		self.keyfile = settings['keyfile']
		self.server_bin = settings['server_bin']

		# We can't use :0 for the forwarding ports because
		# A: It's quite hard to retrieve the port on the remote after the daemon has started
		# B: SSH doesn't accept 0:localhost:0 as a port forwarding option
		[self.local_server_port, self.local_callback_port] = getNPorts(2)
		[self.remote_server_port, self.remote_callback_port] = getNPorts(2)

	def connect(self):
		log.debug('Opening SSH connection')
		import subprocess

		server_cmd = ['sudo', self.settings['server_bin'], '--listen', str(self.remote_server_port)]

		addr_arg = '{user}@{host}'.format(user=self.username, host=self.address)
		ssh_cmd = ['ssh', '-i', self.settings['keyfile'],
		                  '-p', str(self.settings['port']),
		                  '-L' + str(self.local_server_port) + ':localhost:' + str(self.remote_server_port),
		                  '-R' + str(self.remote_callback_port) + ':localhost:' + str(self.local_callback_port),
		                  addr_arg]
		full_cmd = ssh_cmd + ['--'] + server_cmd
		import sys
		self.ssh_process = subprocess.Popen(args=full_cmd, stdout=sys.stderr, stderr=sys.stderr)

		# Check that we can connect to the server
		try:
			import Pyro4
			server_uri = 'PYRO:server@localhost:{server_port}'.format(server_port=self.local_server_port)
			self.connection = Pyro4.Proxy(server_uri)

			log.debug('Connecting to the RPC daemon')
			remaining_retries = 5
			while True:
				try:
					self.connection.ping()
					break
				except (Pyro4.errors.ConnectionClosedError, Pyro4.errors.CommunicationError) as e:
					if remaining_retries > 0:
						remaining_retries -= 1
						from time import sleep
						sleep(2)
					else:
						raise e
		except (Exception, KeyboardInterrupt) as e:
			self.ssh_process.terminate()
			raise e
		return self.connection

	def disconnect(self):
		if hasattr(self, 'connection'):
			log.debug('Stopping the RPC daemon')
			self.connection.stop()
			self.connection._pyroRelease()
		if hasattr(self, 'ssh_process'):
			log.debug('Waiting for the SSH connection to terminate')
			self.ssh_process.wait()

	def download(self, src, dst):
		src_arg = '{user}@{host}:{path}'.format(self.username, self.address, src)
		log_check_call(['scp', '-i', self.keyfile, '-P', self.port,
		                src_arg, dst])

	def delete(self, path):
		ssh_cmd = ['ssh', '-i', self.settings['keyfile'],
		                  '-p', str(self.settings['port']),
		                  self.username + '@' + self.address,
		                  '--',
		                  'sudo', 'rm', path]
		log_check_call(ssh_cmd)


def getNPorts(n, port_range=(1024, 65535)):
	import random
	ports = []
	for i in range(0, n):
		while True:
			port = random.randrange(*port_range)
			if port not in ports:
				ports.append(port)
				break
	return ports
