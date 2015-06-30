from bootstrapvz.base import Task
from bootstrapvz.common import phases
import os.path


class DefaultPackages(Task):
	description = 'Adding image packages required for EC2'
	phase = phases.preparation

	@classmethod
	def run(cls, info):
		info.packages.add('file')  # Needed for the init scripts

		# isc-dhcp-client before jessie doesn't work properly with ec2
		from bootstrapvz.common.releases import jessie
		if info.manifest.release < jessie:
			info.packages.add('dhcpcd')
			info.exclude_packages.add('isc-dhcp-client')
			info.exclude_packages.add('isc-dhcp-common')

		kernel_packages_path = os.path.join(os.path.dirname(__file__), 'packages-kernels.yml')
		from bootstrapvz.common.tools import config_get
		kernel_package = config_get(kernel_packages_path, [info.manifest.release.codename,
		                                                   info.manifest.system['architecture']])
		info.packages.add(kernel_package)


class AddWorkaroundGrowpart(Task):
	description = 'Adding growpart'
	phase = phases.system_modification

	@classmethod
	def run(cls, info):
		from shutil import copy
		from . import assets
		src = os.path.join(assets, 'bin/growpart')
		dst = os.path.join(info.root, 'usr/bin/growpart')
		copy(src, dst)
