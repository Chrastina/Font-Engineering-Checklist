# encoding: utf-8

###########################################################################################################
#
# Font Engineering Checklist
# A QA checklist for your font, as a floating window in Glyphs.
#
# Michal Chrastina & Kasper
# https://github.com/<user>/FontEngineeringChecklist
#
###########################################################################################################

from __future__ import division, print_function, unicode_literals
import json
import os
import objc
from GlyphsApp import Glyphs, WINDOW_MENU, Message
from GlyphsApp.plugins import GeneralPlugin
from AppKit import NSMenuItem

# Stable identifier for state saved inside .glyphs files (font.userData).
# NEVER change this string — users' saved checklist state depends on it.
USERDATA_KEY = "com.michalchrastina.FontEngineeringChecklist"


class FontEngineeringChecklist(GeneralPlugin):

	@objc.python_method
	def settings(self):
		self.name = Glyphs.localize({'en': 'Font Engineering Checklist'})

	@objc.python_method
	def start(self):
		newMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(self.name, self.showWindow_, "")
		newMenuItem.setTarget_(self)
		Glyphs.menu[WINDOW_MENU].append(newMenuItem)

	def showWindow_(self, sender):
		try:
			import vanilla
		except ImportError:
			Message(
				title="Vanilla module missing",
				message="Font Engineering Checklist needs the Vanilla module. Install it in Window > Plugin Manager > Modules, then relaunch Glyphs.",
			)
			return

		data = self.loadChecks()
		lines = []
		for category in data["categories"]:
			count = sum(1 for check in data["checks"] if check["category"] == category["id"])
			lines.append("%s — %i checks" % (category["name"], count))

		# Phase 0: proves the bundle loads, the menu item works and checks.json parses.
		# The real checklist UI lands in Phase 1.
		self.w = vanilla.FloatingWindow((320, 250), self.name)
		self.w.intro = vanilla.TextBox(
			(15, 12, -15, 36),
			"Phase 0 scaffold — %i checks loaded.\nChecklist UI coming in Phase 1." % len(data["checks"]),
			sizeStyle="small",
		)
		self.w.categories = vanilla.TextBox((15, 56, -15, -12), "\n".join(lines), sizeStyle="small")
		self.w.open()

	@objc.python_method
	def loadChecks(self):
		path = os.path.join(os.path.dirname(self.__file__()), "checks.json")
		with open(path, "r", encoding="utf-8") as f:
			return json.load(f)

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
