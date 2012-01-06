#!/usr/bin/env python
'''
owtf is an OWASP+PTES-focused try to unite great tools and facilitate pen testing
Copyright (c) 2011, Abraham Aranguren <name.surname@gmail.com> Twitter: @7a_ http://7-a.org
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the <organization> nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;

The Configuration object parses all configuration files, loads them into memory, derives some settings and provides framework modules with a central repository to get info
'''
import sys, os, re
from collections import defaultdict
from framework.config import plugin
from framework.lib.general import *

# Plugin config offsets for info:
PTYPE = 0
PFILE = 1
PTITLE = 2
PCODE = 3
PURL = 4
DEFAULT_PROFILES = { 'g' : 'DEFAULT_GENERAL_PROFILE', 'net' : 'DEFAULT_NET_PLUGIN_ORDER_PROFILE', 'web' : 'DEFAULT_WEB_PLUGIN_ORDER_PROFILE', 'r' : 'DEFAULT_RESOURCES_PROFILE' } 
REPLACEMENT_DELIMITER = "@@@"
REPLACEMENT_DELIMITER_LENGTH = len(REPLACEMENT_DELIMITER)
CONFIG_TYPES = [ 'string', 'other' ]

class Config:
	Target = None
	def __init__(self, RootDir, CoreObj):
		self.RootDir = RootDir
		self.Core = CoreObj
		self.Config = defaultdict(list) # General configuration information
		for Type in CONFIG_TYPES:
			self.Config[Type] = {} # Distinguish strings from everything else in the config = easier + more efficient to replace resources later
		#print str(self.Config)
		self.TargetConfig = {} # General + Target-specific configuration
		self.Targets = [] # List of targets
		# Available profiles = g -> General configuration, n -> Network plugin order, w -> Web plugin order, r -> Resources file
		self.LoadConfigFromFile( self.RootDir+'/framework/config/framework_config.cfg' )

	def Init(self):
		self.Plugin = plugin.PluginConfig(self.Core)

	def GetTarget(self):
		return self.Target

	def GetTargets(self):
		return self.Targets

	def LoadConfigFromFile(self, ConfigPath): # Load the configuration frominto a global dictionary
		cprint("Loading Config from: "+ConfigPath+" ..")
		ConfigFile = open(ConfigPath, 'r')
		for line in ConfigFile:
			try:
				Key = line.split(':')[0]
				if Key[0] == '#': # Ignore comment lines
					continue
				#Value = ''.join(line.split(':')[1:]).strip() <- Removes ":"!!!
				Value = line.replace(Key+": ", "").strip()
				self.Set(Key, MultipleReplace(Value, { '@@@FRAMEWORK_DIR@@@' : self.RootDir } ))
			except ValueError:
				self.Core.Error.FrameworkAbort("Problem in config file: '"+ConfigPath+"' -> Cannot parse line: "+line)

	def ProcessOptions(self, Options):
                self.Set('FORCE_OVERWRITE', Options['Force_Overwrite']) # True/False
                self.Set('INTERACTIVE', Options['Interactive']) # True/False
                self.Set('SIMULATION', Options['Simulation']) # True/False
		self.Plugin.LoadWebTestGroupsFromFile()
                self.LoadProfiles(Options['Profiles'])
                self.DeriveGlobalSettings()
                self.DeriveFromTarget(Options)

	def DeepCopy(self, Config): # function to perform a "deep" copy of the config Obj passed
		Copy = defaultdict(list)
		for Key, Value in Config.items():
			Copy[Key] = Value.copy()
		return Copy
	
	def SetTarget(self, Target): # Sets the Target Offset in the configuration, until changed Config.Get will retrieve Target-specific info
		self.Target = Target
		if self.Target not in self.TargetConfig: # Target config not initialised yet
			#self.TargetConfig[self.Target] = self.Config.deepcopy() # Clone general info into target-specific config
			self.TargetConfig[self.Target] = self.DeepCopy(self.Config) # Clone general info into target-specific config
			self.Targets.append(self.Target)
		self.Set('TARGET', Target)
		#print str(self.TargetConfig)

	def DeriveFromTarget(self, Options):
		self.TargetConfig = defaultdict(list) # General + Target-specific configuration
		if Options['PluginGroup'] not in [ 'web', 'aux' ]:
			self.Core.Error.FrameworkAbort("Sorry, not implemented yet!")
		if Options['PluginGroup'] == 'web': # Target to be interpreted as a URL
			for TargetURL in Options['Scope']:
				self.SetTarget(TargetURL) # Set the Target URL as the configuration offset, changes will be performed here
				#self.TargetConfig[TargetURL] = self.Config.copy() # Clone general info into target-specific config
                        	self.DeriveConfigFromURL(TargetURL) # Derive some settings from Target URL and initialise everything
				self.Set('REVIEW_OFFSET', TargetURL)
				# All virtual host URLs to be displayed under ip/port in summary:
				self.Set('SUMMARY_HOST_IP', self.Get('HOST_IP')) 
				self.Set('SUMMARY_PORT_NUMBER', self.Get('PORT_NUMBER')) 
				self.Set('REPORT_TYPE', 'URL')
		elif Options['PluginGroup'] == 'aux': # Target to NOT be interpreted as anything
			self.Set('AUX_OUTPUT_PATH', self.Get('OUTPUT_PATH')+"/aux")
			self.Set('HTML_DETAILED_REPORT_PATH', self.Get('OUTPUT_PATH')+"/aux.html") # IMPORTANT: For localStorage to work Url reports must be on the same directory
			self.InitHTTPDBs(self.Get('AUX_OUTPUT_PATH')+"/db/") # Aux modules can make HTTP requests, but these are saved on aux DB
			self.Set('REVIEW_OFFSET', 'AUX')
			self.Set('SUMMARY_HOST_IP', '') 
			self.Set('SUMMARY_PORT_NUMBER', '') 
			self.Set('REPORT_TYPE', 'AUX')
			self.SetTarget('aux') # No Target for Aux plugins -> They work in a different way. But need target here for conf. to work properly

	def LoadProfiles(self, Profiles):
		self.Profiles = defaultdict(list) # This prevents python from blowing up when the Key does not exist :)
		for Type, Setting in DEFAULT_PROFILES.items():
			self.Profiles[Type] = self.Get(Setting) # First set default files for each profile type
		for Type, File in Profiles: # Now override with User-provided profiles, if present
			self.Profiles[Type] = File
		# Now the self.Profiles contains the right mix of default + user-supplied profiles, parse the profiles
		self.LoadConfigFromFile(self.Profiles['g']) # General config loaded on top of normal config
		self.LoadResourcesFromFile(self.Profiles['r'])
		for PluginGroup in self.Plugin.GetAllGroups():
			if PluginGroup in self.Profiles:
				self.Plugin.LoadPluginOrderFromFile(PluginGroup, self.Profiles[PluginGroup])
			else:
				self.Plugin.LoadPluginOrderFromFileSystem(PluginGroup)

	def LoadResourcesFromFile(self, File): # This needs to be a list instead of a dictionary to preserve order in python < 2.7
		cprint("Loading Resources from: "+File+" ..")
		self.ResourcePath = File
		ConfigFile = open(File, 'r')
		self.Resources = defaultdict(list) # This prevents python from blowing up when the Key does not exist :)
		for line in ConfigFile:
			if '#' == line[0]:
				continue # Skip comment lines
			try:
				Type, Name, Resource = line.split('_____')
			except:
				cprint(self.ResourcePath+" ERROR: The delimiter is incorrect in this line: "+str(line.split('_____')))
				sys.exit(-1)
			self.Resources[Type.upper()].append([ Name, Resource ])

	def IsResourceType(self, ResourceType):
		return ResourceType in self.Resources

	def GetResources(self, ResourceType): # Transparently replaces the Resources placeholders with the relevant config information 
		ReplacedResources = []
		ResourceType = ResourceType.upper() # Force upper case to make Resource search not case sensitive
		if self.IsResourceType(ResourceType):
			for Name, Resource in self.Resources[ResourceType]:
				ReplacedResources.append( [ Name, MultipleReplace( Resource, self.GetReplacementDict() ) ] )
		else:
			cprint("The resource type: '"+str(ResourceType)+"' is not defined on '"+self.ResourcePath+"'")
		return ReplacedResources

	def GetResourceList(self, ResourceTypeList):
		ResourceList = []
		for ResourceType in ResourceTypeList:
			#print "ResourceTye="+str(self.GetResources(ResourceType))
			ResourceList = ResourceList + self.GetResources(ResourceType)
		return ResourceList

	def GetRawResources(self, ResourceType):
		return self.Resources[ResourceType]
		
	def DeriveGlobalSettings(self):
		self.Set('FRAMEWORK_DIR', self.RootDir)
		DBPath = self.Get('OUTPUT_PATH')+"/db/" # Global DB
		self.Set('RUN_DB', DBPath+'runs.txt') # Stores when and how owtf was run
		self.Set('ERROR_DB', DBPath+'errors.txt') # Stores error traces for debugging
		self.Set('SEED_DB', DBPath+'seed.txt') # Stores random seed for testing
		self.Set('SUMMARY_HTMLID_DB', DBPath+'htmlid.txt') # Stores the max html element id to ensure unique ids in forms, etc
		self.Set('DEBUG_DB', DBPath+'debug.txt')
		self.Set('PLUGIN_REPORT_REGISTER', DBPath+"plugin_report_register.txt")
		self.Set('DETAILED_REPORT_REGISTER', DBPath+"detailed_report_register.txt")

		self.Set('USER_AGENT_#', self.Get('USER_AGENT').replace(' ', '#')) # User-Agent as shell script-friendly argument! :)
		self.Set('SHORT_USER_AGENT', self.Get('USER_AGENT').split(' ')[0]) # For tools that choke with blank spaces in UA!?
		self.Set('HTML_REPORT_PATH', self.Get('OUTPUT_PATH')+"/"+self.Get('HTML_REPORT'))

	def DeriveURLSettings(self, TargetURL):
		if TargetURL[-1] == "/":
			TargetURL = TargetURL[0:-1]
		if TargetURL[0:4] != 'http':
			TargetURL = 'http://'+TargetURL # Add "http" if not present
		#print "self.Target="+self.Target
		self.Set('TARGET_URL', TargetURL) # Set the target in the config	
		protocol, crap, host = TargetURL.split('/')[0:3]
		DotChunks = TargetURL.split(':')
		Port = '80'
		if len(DotChunks) == 2: # Case: http://myhost.com -> Derive port from http / https
			if 'https' == DotChunks[0]:
				Port = '443'	
		else: # Derive port from ":xyz" URL part
			Port = DotChunks[2].split('/')[0]	

		self.Set('PORT_NUMBER', Port) # Some tools need this!
		self.Set('HOST_NAME', host) # Set the top URL
                self.Set('HOST_IP', self.GetIPFromHostname(self.Get('HOST_NAME')))

                self.Set('IP_URL', self.Get('TARGET_URL').replace(self.Get('HOST_NAME'), self.Get('HOST_IP')))
                self.Set('TOP_DOMAIN', self.Get('HOST_NAME'))
                HostnameChunks = self.Get('HOST_NAME').split('.')
                if self.IsHostNameNOTIP() and len(HostnameChunks) > 2:
                        self.Set('TOP_DOMAIN', '.'.join(HostnameChunks[1:])) #Get "example.com" from "www.example.com"
		self.Set('TOP_URL', protocol+"//"+host) # Set the top URL

	def DeriveOutputSettingsFromURL(self, TargetURL):
		self.Set('HOST_OUTPUT', self.Get('OUTPUT_PATH')+"/"+self.Get('HOST_IP')) # Set the output directory
		self.Set('PORT_OUTPUT', self.Get('HOST_OUTPUT')+"/"+self.Get('PORT_NUMBER')) # Set the output directory
		URLInfoID = TargetURL.replace('/','_').replace(':','')
		self.Set('URL_OUTPUT', self.Get('PORT_OUTPUT')+"/"+URLInfoID+"/") # Set the URL output directory (plugins will save their data here)
		self.Set('PARTIAL_URL_OUTPUT_PATH', self.Get('URL_OUTPUT')+'partial') # Set the partial results path
		self.Set('PARTIAL_REPORT_REGISTER', self.Get('PARTIAL_URL_OUTPUT_PATH')+"/partial_report_register.txt")

		# Tested in FF 8: Different directory = Different localStorage!! -> All localStorage-dependent reports must be on the same directory
		self.Set('HTML_DETAILED_REPORT_PATH', self.Get('OUTPUT_PATH')+"/"+URLInfoID+".html") # IMPORTANT: For localStorage to work Url reports must be on the same directory
		self.Set('URL_REPORT_LINK_PATH', self.Get('OUTPUT_PATH')+"/index.html") # IMPORTANT: For localStorage to work Url reports must be on the same directory

		if not self.Get('SIMULATION'):
			self.Core.CreateMissingDirs(self.Get('HOST_OUTPUT'))

		# URL Analysis DBs
		# URL DBs: Distintion between vetted, confirmed-to-exist, in transaction DB URLs and potential URLs
		self.InitHTTPDBs(self.Get('URL_OUTPUT'))

	def InitHTTPDBs(self, DBPath):
		self.Set('TRANSACTION_LOG_TXT', DBPath+'transaction_log.txt') # Set the Transaction database
		self.Set('TRANSACTION_LOG_HTML', DBPath+'transaction_log.html') 
		self.Set('TRANSACTION_LOG_TRANSACTIONS', DBPath+'transactions/') # directory to store full requests
		self.Set('TRANSACTION_LOG_REQUESTS', DBPath+'transactions/requests/') # directory to store full requests
		self.Set('TRANSACTION_LOG_RESPONSE_HEADERS', DBPath+'transactions/response_headers/') # directory to store full requests
		self.Set('TRANSACTION_LOG_RESPONSE_BODIES', DBPath+'transactions/response_bodies/') # directory to store full requests
		self.Set('TRANSACTION_LOG_FILES', DBPath+'files/') # directory to store downloaded files

		DBPath = DBPath+"db/"
		self.Set('HTMLID_DB', DBPath+'htmlid.txt') # Stores the max html element id to ensure unique ids in forms, etc
		self.Set('ALL_URLS_DB', DBPath+'all_urls.txt') # All URLs in scope without errors
		self.Set('ERROR_URLS_DB', DBPath+'error_urls.txt') # URLs that produce errors (404, etc)
		self.Set('FILE_URLS_DB', DBPath+'file_urls.txt') # URL for files
		self.Set('IMAGE_URLS_DB', DBPath+'image_urls.txt') # URLs for images
		self.Set('FUZZABLE_URLS_DB', DBPath+'fuzzable_urls.txt') # Potentially fuzzable URLs
		self.Set('EXTERNAL_URLS_DB', DBPath+'external_urls.txt') # Out of scope URLs

		self.Set('POTENTIAL_ALL_URLS_DB', DBPath+'potential_urls.txt') # All seen URLs
		# POTENTIAL_ERROR_URLS is never used in the DB but helps simplify the code (vetted urls more similar to potential urls)
		self.Set('POTENTIAL_ERROR_URLS_DB', DBPath+'potential_error_urls.txt') # URLs that produce errors (404, etc) - NOT USED
		self.Set('POTENTIAL_FILE_URLS_DB', DBPath+'potential_file_urls.txt') # URL for files
		self.Set('POTENTIAL_IMAGE_URLS_DB', DBPath+'potential_image_urls.txt') # URLs for images 
		self.Set('POTENTIAL_FUZZABLE_URLS_DB', DBPath+'potential_fuzzable_urls.txt') # Potentially fuzzable URLs
		self.Set('POTENTIAL_EXTERNAL_URLS_DB', DBPath+'potential_external_urls.txt') # Out of scope URLs

	def DeriveConfigFromURL(self, TargetURL): # Basic configuration tweaks to make things simpler for the plugins
		self.DeriveURLSettings(TargetURL)
		self.DeriveOutputSettingsFromURL(TargetURL)

	def GetFileName(self, Setting, Partial = False):
		Path = self.Get(Setting)
		if Partial:
			return Path.split("/")[-1]
		return Path

	def GetHTMLTransacLog(self, Partial = False):
		return self.GetFileName('TRANSACTION_LOG_HTML', Partial)

	def GetTXTTransacLog(self, Partial = False):
		return self.GetFileName('TRANSACTION_LOG_TXT', Partial)

        def IsHostNameNOTIP(self):
                return self.Get('HOST_NAME') != self.Get('HOST_IP') # Host

        def GetIPFromHostname(self, hostname):
                ip = ''
                if len(hostname.split('.')) == 4:
                        ip=hostname #hostname = IPv4 address
                elif len(hostname.split(':')) == 4:
                        ip=hostname #hostname = IPv6 address
                else: #Try to resolve address (IPv4 only!)
                        ip=self.Core.Shell.shell_exec('host '+hostname+'|grep "has address"|cut -f4 -d" "')
		ipchunks = ip.strip().split("\n")
		AlternativeIPs = []
		if len(ipchunks) > 1:
			ip = ipchunks[0]
			cprint(hostname+" has several IP addresses: ("+", ".join(ipchunks)[0:-3]+"). Choosing first: "+ip+"")
			AlternativeIPs = ipchunks[1:]
		self.Set('ALTERNATIVE_IPS', AlternativeIPs)
                ip = ip.strip()
		if len(ip.split('.')) != 4: # TODO: Add IPv6 support!
			self.Core.Error.FrameworkAbort("Cannot resolve hostname: "+hostname)
		# Good IPv4 IP
		self.Set('INTERNAL_IP', self.Core.IsIPInternal(ip))
		cprint("The IP address for "+hostname+" is: '"+ip+"'")
		return ip

	def GetAll(self, Key): # Retrieves a config setting value on all target configurations
		Matches = []
		PreviousTarget = self.Target
		for Target, Config in self.TargetConfig.items():
			self.SetTarget(Target)
			Value = self.Get(Key)
			if Value not in Matches: # Avoid duplicates
				Matches.append(Value)
		self.Target = PreviousTarget
		return Matches

	def IsSet(self, Key):
		Key = self.PadKey(Key)
		Config = self.GetConfig()
		for Type in CONFIG_TYPES:
			if Key in Config[Type]:
				return True
		return False

	def GetKeyValue(self, Key):
		Config = self.GetConfig() # Gets the right config for target / general
		for Type in CONFIG_TYPES:
			if Key in Config[Type]:
				return Config[Type][Key]

	def PadKey(self, Key):
		return REPLACEMENT_DELIMITER+Key+REPLACEMENT_DELIMITER # Add delimiters

	def Get(self, Key): # Transparently gets config info from Target or General
		try:
			Key = self.PadKey(Key)
			return self.GetKeyValue(Key)
		except KeyError:
			Message = "The configuration item: '"+Key+"' does not exist!"
			self.Core.Error.Add(Message)
			raise PluginAbortException(Message) # Raise plugin-level exception to move on to next plugin

	def GetAsPartialPath(self, Key): # Convenience wrapper
		return self.Core.GetPartialPath(self.Get(Key))

	def GetAsList(self, KeyList):
		ValueList = []
		for Key in KeyList:
			ValueList.append(self.Get(Key))
		return ValueList

	def GetHeaderList(self, Key):
		return self.Get(Key).split(',')

	def SetForTarget(self, Type, Key, Value, Target):
		#print str(self.TargetConfig)
		#print "Trying .. self.TargetConfig["+Target+"]["+Key+"] = "+Value+" .."
		self.TargetConfig[Target][Type][Key] = Value

	def SetGeneral(self, Type, Key, Value):
		#print str(self.Config)
		self.Config[Type][Key] = Value

	def Set(self, Key, Value): # Transparently set config items in Target-specific or General config
		Key = REPLACEMENT_DELIMITER+Key+REPLACEMENT_DELIMITER # Store config in "replacement mode", that way we can multiple-replace the config on resources, etc
		Type = 'other'
		if isinstance(Value, str): # Only when value is a string, store in replacements config 
			Type = 'string'
		if self.Target == None:
			return self.SetGeneral(Type, Key, Value)
		return self.SetForTarget(Type, Key, Value, self.Target)

	def GetReplacementDict(self):
		return self.GetConfig()['string']

	def __getitem__(self, Key):
		return self.Get(Key)

	def __setitem__(self, Key, Value):
		return self.Set(Key, Value)

	def GetConfig(self):
		if self.Target == None:
			return self.Config
		return self.TargetConfig[self.Target]

	def Show(self):
		cprint("Configuration settings")
		for k, v in self.GetConfig().items():
			cprint(str(k)+" => "+str(v))

