# encoding: utf-8

###########################################################################################################
#
# Font Engineering Checklist
# A QA checklist for your font, as a floating window in Glyphs.
#
# Michal Chrastina & Kasper Pyndt
# https://github.com/Chrastina/Font-Engineering-Checklist
#
###########################################################################################################

from __future__ import division, print_function, unicode_literals
import json
import os
import time
import uuid
import objc
from GlyphsApp import Glyphs, WINDOW_MENU, DOCUMENTOPENED, DOCUMENTACTIVATED, DOCUMENTCLOSED, Message
from GlyphsApp.plugins import GeneralPlugin
from AppKit import (
	NSMenuItem, NSWorkspace, NSURL, NSView, NSImage, NSColor, NSFont,
	NSAttributedString, NSForegroundColorAttributeName, NSFontAttributeName,
)

try:
	import vanilla
	HAS_VANILLA = True
except ImportError:
	HAS_VANILLA = False

# Stable identifier for state saved inside .glyphs files (font.userData).
# NEVER change this string — users' saved checklist state depends on it.
USERDATA_KEY = "com.michalchrastina.FontEngineeringChecklist"
HIDDEN_KEY = USERDATA_KEY + ".hiddenChecks"
CUSTOM_KEY = USERDATA_KEY + ".customChecks"
COLLAPSED_KEY = USERDATA_KEY + ".collapsedCategories"
ORDER_KEY = USERDATA_KEY + ".categoryOrder"

STATE_UNCHECKED = 0
STATE_CHECKED = 1   # ticked manually
STATE_VERIFIED = 2  # ticked by a checker (Phase 2)

MARGIN = 15
ROW_HEIGHT = 24
HEADER_HEIGHT = 28

NS_VIEW_WIDTH_SIZABLE = 2
NS_BEZEL_DISCLOSURE = 5
NS_BUTTON_TYPE_PUSHONPUSHOFF = 1


# A flipped document view keeps short content pinned to the top of the scroll
# area instead of the bottom.
try:
	FECFlippedDocumentView = objc.lookUpClass("FECFlippedDocumentView")
except objc.error:
	class FECFlippedDocumentView(NSView):
		def isFlipped(self):
			return True


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
		if not HAS_VANILLA:
			Message(
				title="Vanilla module missing",
				message="Font Engineering Checklist needs the Vanilla module. Install it in Window > Plugin Manager > Modules, then relaunch Glyphs.",
			)
			return
		if getattr(self, "w", None) is not None:
			self.w.show()
			return
		self.data = self.loadChecks()
		self.editMode = False
		self.buildWindow()

	# ---------------------------------------------------------------- window

	@objc.python_method
	def buildWindow(self):
		self.checkboxRefs = {}
		self.catCountBoxes = {}
		self.popover = None
		self.popoverCheckId = None

		self.w = vanilla.FloatingWindow(
			(400, 560), self.name,
			minSize=(400, 320), maxSize=(1000, 1600),
			autosaveName=USERDATA_KEY + ".mainWindow",
		)
		self.w.fontName = vanilla.TextBox((MARGIN, 10, -120, 17), "")
		self.w.progressText = vanilla.TextBox((-115, 12, -MARGIN, 14), "", alignment="right", sizeStyle="small")
		self.w.progressBar = vanilla.ProgressBar((MARGIN, 33, -MARGIN, 12), minValue=0, maxValue=100)
		self.w.topDivider = vanilla.HorizontalLine((0, 53, -0, 1))
		self.w.bottomDivider = vanilla.HorizontalLine((0, -43, -0, 1))
		self.w.addButton = vanilla.Button(
			(MARGIN, -33, 90, 20), "＋ Add Check", sizeStyle="small", callback=self.openAddSheet)
		self.w.editButton = vanilla.Button(
			(-60, -32, 45, 18), "Edit", sizeStyle="small", callback=self.toggleEditMode)
		self.w.editButton.getNSButton().setBordered_(False)
		self.styleEditButton("Edit")

		self.rebuildList()
		self.updateHeader()

		Glyphs.addCallback(self.documentChanged, DOCUMENTOPENED)
		Glyphs.addCallback(self.documentChanged, DOCUMENTACTIVATED)
		Glyphs.addCallback(self.documentChanged, DOCUMENTCLOSED)
		self.w.bind("close", self.windowClosed)
		self.w.bind("resize", self.syncContentWidth)
		self.w.open()

	@objc.python_method
	def windowClosed(self, sender):
		for signal in (DOCUMENTOPENED, DOCUMENTACTIVATED, DOCUMENTCLOSED):
			try:
				Glyphs.removeCallback(self.documentChanged, signal)
			except Exception:
				pass
		self.w = None

	@objc.python_method
	def documentChanged(self, info=None):
		if getattr(self, "w", None) is None:
			return
		self.updateHeader()
		self.rebuildList()

	@objc.python_method
	def updateHeader(self):
		font = Glyphs.font
		if font is None:
			self.w.fontName.set("No font open — open a font to start ticking.")
		else:
			self.w.fontName.set(font.familyName or "Unnamed font")

	@objc.python_method
	def styleEditButton(self, title):
		attributed = NSAttributedString.alloc().initWithString_attributes_(title, {
			NSForegroundColorAttributeName: NSColor.labelColor(),
			NSFontAttributeName: NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()),
		})
		self.w.editButton.getNSButton().setAttributedTitle_(attributed)

	@objc.python_method
	def toggleEditMode(self, sender):
		self.editMode = not self.editMode
		self.styleEditButton("Done" if self.editMode else "Edit")
		self.rebuildList()

	# ------------------------------------------------------------- main list

	@objc.python_method
	def rebuildList(self):
		scrollY = 0
		if hasattr(self.w, "scroll"):
			try:
				scrollY = self.w.scroll.getNSScrollView().contentView().documentVisibleRect().origin.y
			except Exception:
				pass
			del self.w.scroll
		self.checkboxRefs = {}
		self.catCountBoxes = {}

		font = Glyphs.font
		states = self.getStates(font)
		hidden = set(self.getHidden())
		collapsed = set(self.getCollapsed())
		checksByCat = self.checksByCategory()
		contentWidth = self.w.getPosSize()[2]

		# In edit mode every check is listed (so hidden ones can be unhidden);
		# in normal mode hidden checks and fully hidden categories disappear.
		layout = []
		height = 6
		for category in self.orderedCategories():
			catChecks = checksByCat.get(category["id"], [])
			if not self.editMode:
				catChecks = [c for c in catChecks if c["id"] not in hidden]
				if not catChecks:
					continue
			isCollapsed = category["id"] in collapsed
			layout.append((category, catChecks, isCollapsed))
			height += HEADER_HEIGHT
			if not isCollapsed:
				height += len(catChecks) * ROW_HEIGHT
			height += 4
		height += 6

		group = vanilla.Group((0, 0, contentWidth, height))
		y = 6
		for category, catChecks, isCollapsed in layout:
			catId = category["id"]
			safeCat = self.safeAttr(catId)

			# The native disclosure control — the same triangle Glyphs'
			# palettes use.
			disclose = vanilla.Button(
				(MARGIN - 4, y + 6, 16, 16), "",
				callback=lambda sender, cid=catId: self.toggleCollapsed(cid),
			)
			discloseNSButton = disclose.getNSButton()
			discloseNSButton.setTitle_("")
			# The AppKit disclosure recipe: push-on-push-off type first, then
			# the disclosure bezel — any other type ignores the state and
			# always draws the closed triangle.
			discloseNSButton.setButtonType_(NS_BUTTON_TYPE_PUSHONPUSHOFF)
			discloseNSButton.setBezelStyle_(NS_BEZEL_DISCLOSURE)
			discloseNSButton.setState_(0 if isCollapsed else 1)
			setattr(group, "disclose_%s" % safeCat, disclose)

			label = vanilla.TextBox((MARGIN + 16, y + 8, -130, 15), category["name"], sizeStyle="small")
			label.getNSTextField().setFont_(NSFont.boldSystemFontOfSize_(NSFont.smallSystemFontSize()))
			setattr(group, "label_%s" % safeCat, label)

			if self.editMode:
				up = vanilla.Button(
					(-115, y + 7, 18, 16), "↑", sizeStyle="small",
					callback=lambda sender, cid=catId: self.moveCategory(cid, -1),
				)
				up.getNSButton().setBordered_(False)
				setattr(group, "up_%s" % safeCat, up)
				down = vanilla.Button(
					(-97, y + 7, 18, 16), "↓", sizeStyle="small",
					callback=lambda sender, cid=catId: self.moveCategory(cid, 1),
				)
				down.getNSButton().setBordered_(False)
				setattr(group, "down_%s" % safeCat, down)

			countBox = vanilla.TextBox((-80, y + 9, -(MARGIN - 2), 14), "", alignment="right", sizeStyle="small")
			setattr(group, "count_%s" % safeCat, countBox)
			self.catCountBoxes[catId] = countBox
			y += HEADER_HEIGHT

			if not isCollapsed:
				for check in catChecks:
					self.buildRow(group, check, states, font, hidden, y)
					y += ROW_HEIGHT
			y += 4

		documentView = FECFlippedDocumentView.alloc().initWithFrame_(((0, 0), (contentWidth, height)))
		documentView.setAutoresizingMask_(NS_VIEW_WIDTH_SIZABLE)
		groupView = group.getNSView()
		groupView.setFrame_(((0, 0), (contentWidth, height)))
		groupView.setAutoresizingMask_(NS_VIEW_WIDTH_SIZABLE)
		documentView.addSubview_(groupView)

		self._contentGroup = group
		self.w.scroll = vanilla.ScrollView(
			(0, 54, -0, -44), documentView,
			hasHorizontalScroller=False, drawsBackground=False,
		)
		nsScrollView = self.w.scroll.getNSScrollView()
		# Overlay scrollers: transparent, no white track, and they reserve no
		# layout width.
		nsScrollView.setScrollerStyle_(1)
		self.syncContentWidth()
		if scrollY:
			documentView.scrollPoint_((0, scrollY))
		self.updateCounts()

	@objc.python_method
	def syncContentWidth(self, sender=None):
		# The clip view does NOT autoresize its document view when the window
		# resizes — this syncs the content width, and the autoresizing masks
		# inside take care of the right-anchored controls.
		if getattr(self, "w", None) is None or not hasattr(self.w, "scroll"):
			return
		try:
			nsScrollView = self.w.scroll.getNSScrollView()
			clipSize = nsScrollView.contentView().frame().size
			documentView = nsScrollView.documentView()
			docSize = documentView.frame().size
			if int(docSize.width) != int(clipSize.width):
				documentView.setFrameSize_((clipSize.width, docSize.height))
		except Exception:
			pass

	@objc.python_method
	def buildRow(self, group, check, states, font, hidden, y):
		# The title is always its own text column at a fixed x, so swapping the
		# control (checkbox vs. eye) never shifts the text.
		safeCheck = self.safeAttr(check["id"])
		isHidden = check["id"] in hidden
		controlX = MARGIN + 6
		titleX = MARGIN + 31

		if self.editMode:
			eyeImage = self.eyeImage(not isHidden)
			if eyeImage is not None:
				eye = vanilla.ImageButton(
					(controlX, y + 3, 18, 16), imageObject=eyeImage, bordered=False,
					callback=lambda sender, cid=check["id"]: self.visibilityToggled(cid),
				)
			else:
				eye = vanilla.Button(
					(controlX, y + 3, 18, 16), "👁" if not isHidden else "–", sizeStyle="small",
					callback=lambda sender, cid=check["id"]: self.visibilityToggled(cid),
				)
				eye.getNSButton().setBordered_(False)
			setattr(group, "eye_%s" % safeCheck, eye)
		else:
			state = states.get(check["id"], 0)
			box = vanilla.CheckBox(
				(controlX, y + 2, 18, 18), "",
				value=state > 0, sizeStyle="small",
				callback=lambda sender, cid=check["id"]: self.checkToggled(sender, cid),
			)
			if font is None:
				box.enable(False)
			setattr(group, "check_%s" % safeCheck, box)
			self.checkboxRefs[check["id"]] = box

		title = check["title"]
		if self.editMode and check.get("custom"):
			title += "  (custom)"
		label = vanilla.TextBox((titleX, y + 5, -40, 16), title, sizeStyle="small")
		if self.editMode and isHidden:
			label.getNSTextField().setTextColor_(NSColor.secondaryLabelColor())
		setattr(group, "title_%s" % safeCheck, label)

		if self.editMode:
			if check.get("custom"):
				remove = vanilla.Button(
					(-(MARGIN + 16), y + 4, 16, 16), "−", sizeStyle="small",
					callback=lambda sender, cid=check["id"]: self.removeCustomCheck(cid),
				)
				remove.getNSButton().setBordered_(False)
				setattr(group, "remove_%s" % safeCheck, remove)
		else:
			info = vanilla.Button(
				(-(MARGIN + 16), y + 4, 16, 16), "ⓘ", sizeStyle="small",
				callback=lambda sender, cid=check["id"]: self.showInfo(sender, cid),
			)
			info.getNSButton().setBordered_(False)
			setattr(group, "info_%s" % safeCheck, info)

	@objc.python_method
	def eyeImage(self, visible):
		# The same template images Glyphs' own Layers palette uses.
		image = NSImage.imageNamed_("GSVisibleTemplate" if visible else "GSInvisibleTemplate")
		if image is None and hasattr(NSImage, "imageWithSystemSymbolName_accessibilityDescription_"):
			image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
				"eye" if visible else "eye.slash", None)
		return image

	@objc.python_method
	def checkToggled(self, sender, checkId):
		font = Glyphs.font
		if font is None:
			sender.set(False)
			return
		newState = STATE_CHECKED if sender.get() else STATE_UNCHECKED
		self.setState(font, checkId, newState)
		self.updateCounts()

	@objc.python_method
	def visibilityToggled(self, checkId):
		hidden = set(self.getHidden())
		if checkId in hidden:
			hidden.remove(checkId)
		else:
			hidden.add(checkId)
		Glyphs.defaults[HIDDEN_KEY] = sorted(hidden)
		self.rebuildList()

	@objc.python_method
	def toggleCollapsed(self, catId):
		collapsed = set(self.getCollapsed())
		if catId in collapsed:
			collapsed.remove(catId)
		else:
			collapsed.add(catId)
		Glyphs.defaults[COLLAPSED_KEY] = sorted(collapsed)
		self.rebuildList()

	@objc.python_method
	def moveCategory(self, catId, delta):
		order = [c["id"] for c in self.orderedCategories()]
		i = order.index(catId)
		j = i + delta
		if j < 0 or j >= len(order):
			return
		order[i], order[j] = order[j], order[i]
		Glyphs.defaults[ORDER_KEY] = order
		self.rebuildList()

	@objc.python_method
	def removeCustomCheck(self, checkId):
		Glyphs.defaults[CUSTOM_KEY] = [c for c in self.plainCustomChecks() if c["id"] != checkId]
		Glyphs.defaults[HIDDEN_KEY] = [h for h in self.getHidden() if h != checkId]
		self.rebuildList()

	@objc.python_method
	def updateCounts(self):
		states = self.getStates(Glyphs.font)
		hidden = set(self.getHidden())
		checksByCat = self.checksByCategory()
		total = done = 0
		for category in self.data["categories"]:
			catId = category["id"]
			catTotal = catDone = 0
			for check in checksByCat.get(catId, []):
				if check["id"] in hidden:
					continue
				catTotal += 1
				if states.get(check["id"], 0) > 0:
					catDone += 1
			if catId in self.catCountBoxes:
				self.catCountBoxes[catId].set("%i/%i" % (catDone, catTotal))
			total += catTotal
			done += catDone
		percent = int(round(done * 100.0 / total)) if total else 0
		self.w.progressBar.set(percent)
		self.w.progressText.set("%i %% (%i/%i)" % (percent, done, total))

	# ------------------------------------------------------------- info popover

	@objc.python_method
	def showInfo(self, sender, checkId):
		# Toggle: clicking the ⓘ of the open popover closes it. State is
		# cleared before closing so the "did close" handler doesn't arm the
		# reopen guard — otherwise the next click would be swallowed.
		if self.popover is not None and self.popoverCheckId == checkId:
			popover = self.popover
			self.popover = None
			self.popoverCheckId = None
			self._lastClosedId = None
			try:
				popover.close()
			except Exception:
				pass
			return
		# A transient popover closes on the mouse-down of this very click,
		# before the button action fires — don't immediately reopen it.
		if (
			getattr(self, "_lastClosedId", None) == checkId
			and time.time() - getattr(self, "_lastClosedTime", 0) < 0.4
		):
			self._lastClosedId = None
			return

		check = next((c for c in self.allChecks() if c["id"] == checkId), None)
		if check is None:
			return
		title = check["title"]
		info = check.get("info", "") or "No description yet."
		links = check.get("links", []) or []

		width = 320
		textHeight = max(34, (len(info) // 46 + info.count("\n") + 1) * 15 + 8)
		height = 10 + 18 + textHeight + len(links) * 24 + 8

		self.popover = vanilla.Popover((width, height), behavior="transient")
		self.popoverCheckId = checkId
		self.popover.title = vanilla.TextBox((10, 8, -10, 16), title, sizeStyle="small")
		self.popover.text = vanilla.TextBox((10, 28, -10, textHeight), info, sizeStyle="small")
		y = 28 + textHeight + 2
		for i, link in enumerate(links):
			button = vanilla.Button(
				(10, y, -10, 18), "↗ %s" % link["label"], sizeStyle="small",
				callback=lambda sender, url=link["url"]: self.openURL(url),
			)
			setattr(self.popover, "link_%i" % i, button)
			y += 24
		self.popover.bind("did close", self.popoverDidClose)
		self.popover.open(parentView=sender, preferredEdge="right")

	@objc.python_method
	def popoverDidClose(self, sender):
		self._lastClosedId = self.popoverCheckId
		self._lastClosedTime = time.time()
		self.popover = None
		self.popoverCheckId = None

	@objc.python_method
	def openURL(self, url):
		NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))

	# ------------------------------------------------------------- custom checks

	@objc.python_method
	def openAddSheet(self, sender):
		categoryNames = [c["name"] for c in self.orderedCategories()]
		self.addSheet = vanilla.Sheet((380, 250), self.w)
		self.addSheet.titleLabel = vanilla.TextBox((MARGIN, 17, 65, 16), "Title", sizeStyle="small")
		self.addSheet.titleField = vanilla.EditText((85, 14, -MARGIN, 22), "")
		self.addSheet.catLabel = vanilla.TextBox((MARGIN, 49, 65, 16), "Category", sizeStyle="small")
		self.addSheet.catPopup = vanilla.PopUpButton((85, 46, -MARGIN, 22), categoryNames)
		self.addSheet.infoLabel = vanilla.TextBox((MARGIN, 81, 65, 16), "Info", sizeStyle="small")
		self.addSheet.infoField = vanilla.TextEditor((85, 78, -MARGIN, -50), "")
		self.addSheet.cancelButton = vanilla.Button((-185, -35, 80, 20), "Cancel", callback=self.addSheetCancel)
		self.addSheet.addButton = vanilla.Button((-95, -35, 80, 20), "Add", callback=self.addSheetAdd)
		self.addSheet.setDefaultButton(self.addSheet.addButton)
		self.addSheet.open()

	@objc.python_method
	def addSheetCancel(self, sender):
		self.addSheet.close()

	@objc.python_method
	def addSheetAdd(self, sender):
		title = self.addSheet.titleField.get().strip()
		if not title:
			Message(title="Missing title", message="Give the check a title first.")
			return
		category = self.orderedCategories()[self.addSheet.catPopup.get()]["id"]
		info = self.addSheet.infoField.get().strip()
		custom = self.plainCustomChecks()
		custom.append({
			"id": "custom-%s" % uuid.uuid4().hex[:12],
			"title": title,
			"category": category,
			"info": info,
		})
		Glyphs.defaults[CUSTOM_KEY] = custom
		self.addSheet.close()
		self.rebuildList()

	# ------------------------------------------------------------- data: checks

	@objc.python_method
	def loadChecks(self):
		path = os.path.join(os.path.dirname(self.__file__()), "checks.json")
		with open(path, "r", encoding="utf-8") as f:
			return json.load(f)

	@objc.python_method
	def orderedCategories(self):
		categories = list(self.data["categories"])
		order = Glyphs.defaults[ORDER_KEY]
		if order:
			order = [str(x) for x in order]
			position = {catId: i for i, catId in enumerate(order)}
			categories.sort(key=lambda c: position.get(c["id"], len(order)))
		return categories

	@objc.python_method
	def allChecks(self):
		return list(self.data["checks"]) + self.getCustomChecks()

	@objc.python_method
	def checksByCategory(self):
		byCat = {}
		for check in self.allChecks():
			byCat.setdefault(check["category"], []).append(check)
		return byCat

	@objc.python_method
	def getCustomChecks(self):
		value = Glyphs.defaults[CUSTOM_KEY]
		result = []
		if value:
			for item in value:
				try:
					result.append({
						"id": str(item["id"]),
						"title": str(item["title"]),
						"category": str(item["category"]),
						"info": str(item["info"]) if "info" in item and item["info"] else "",
						"type": "manual",
						"custom": True,
					})
				except (KeyError, TypeError):
					continue
		return result

	@objc.python_method
	def plainCustomChecks(self):
		return [
			{"id": c["id"], "title": c["title"], "category": c["category"], "info": c["info"]}
			for c in self.getCustomChecks()
		]

	@objc.python_method
	def getHidden(self):
		value = Glyphs.defaults[HIDDEN_KEY]
		return [str(x) for x in value] if value else []

	@objc.python_method
	def getCollapsed(self):
		value = Glyphs.defaults[COLLAPSED_KEY]
		return [str(x) for x in value] if value else []

	# ------------------------------------------------------------- data: state

	@objc.python_method
	def getStates(self, font):
		"""Checked-state dict {checkId: int} from the font, safe against missing data."""
		if font is None:
			return {}
		data = font.userData[USERDATA_KEY]
		if data is None:
			return {}
		try:
			states = data["states"]
		except (KeyError, TypeError):
			return {}
		if states is None:
			return {}
		result = {}
		for key in states.keys():
			try:
				result[str(key)] = int(states[key])
			except (TypeError, ValueError):
				pass
		return result

	@objc.python_method
	def setState(self, font, checkId, value):
		# Re-writes the whole dict so unknown keys (e.g. another user's custom
		# checks) are preserved, never pruned.
		data = self.plainCopy(font.userData[USERDATA_KEY])
		if not isinstance(data, dict):
			data = {}
		data.setdefault("v", 1)
		states = data.get("states")
		if not isinstance(states, dict):
			states = {}
		states[str(checkId)] = int(value)
		data["states"] = states
		font.userData[USERDATA_KEY] = data

	@objc.python_method
	def plainCopy(self, value):
		"""Deep-copies NSDictionary/NSArray structures into plain Python."""
		if value is None:
			return None
		if isinstance(value, str):
			return str(value)
		if hasattr(value, "keys"):
			return {str(key): self.plainCopy(value[key]) for key in value.keys()}
		if hasattr(value, "__iter__"):
			return [self.plainCopy(item) for item in value]
		return value

	# ------------------------------------------------------------- helpers

	@objc.python_method
	def safeAttr(self, identifier):
		return identifier.replace("-", "_").replace(".", "_")

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
