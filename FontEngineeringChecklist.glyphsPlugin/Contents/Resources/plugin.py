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
	NSApp, NSMenuItem, NSWorkspace, NSURL, NSView, NSImage, NSColor, NSFont,
	NSAttributedString, NSForegroundColorAttributeName, NSFontAttributeName,
	NSButton, NSNotificationCenter,
	NSMutableParagraphStyle, NSParagraphStyleAttributeName,
)

try:
	import vanilla
	HAS_VANILLA = True
except ImportError:
	HAS_VANILLA = False

# The checker functions live next to this file; the unique module name avoids
# collisions with other plugins doing the same sys.path trick.
import sys
_RESOURCES_DIR = os.path.dirname(__file__)
if _RESOURCES_DIR not in sys.path:
	sys.path.insert(0, _RESOURCES_DIR)
import fec_checkers

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
NS_VIEW_MIN_X_MARGIN = 1
NS_BEZEL_DISCLOSURE = 5
NS_BUTTON_TYPE_PUSHONPUSHOFF = 1
NSVIEW_FRAME_CHANGED = "NSViewFrameDidChangeNotification"


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
			self.makeWindowKey()
			self.performSelector_withObject_afterDelay_("makeWindowKey", None, 0.1)
			return
		self.data = self.loadChecks()
		self.editMode = False
		self.buildWindow()

	def makeWindowKey(self):
		if getattr(self, "w", None) is None:
			return
		try:
			panel = self.w.getNSWindow()
			panel.setBecomesKeyOnlyIfNeeded_(False)
			panel.makeKeyAndOrderFront_(None)
		except Exception:
			pass

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
		# Open as the key window right away — otherwise the panel draws in
		# the inactive grey appearance until its title bar is clicked. The
		# delayed second call wins over whoever steals focus right after the
		# menu action.
		self.makeWindowKey()
		self.performSelector_withObject_afterDelay_("makeWindowKey", None, 0.1)

	@objc.python_method
	def windowClosed(self, sender):
		for signal in (DOCUMENTOPENED, DOCUMENTACTIVATED, DOCUMENTCLOSED):
			try:
				Glyphs.removeCallback(self.documentChanged, signal)
			except Exception:
				pass
		NSNotificationCenter.defaultCenter().removeObserver_name_object_(self, NSVIEW_FRAME_CHANGED, None)
		self.w = None

	def clipFrameChanged_(self, notification):
		if getattr(self, "_rebuilding", False):
			return
		self.syncContentWidth()

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
	def rightAlignedTitle(self, title):
		# Buttons center their titles; the paragraph style pushes the text to
		# the right edge of the frame so it sits flush on the margin.
		paragraph = NSMutableParagraphStyle.alloc().init()
		paragraph.setAlignment_(1)
		return NSAttributedString.alloc().initWithString_attributes_(title, {
			NSForegroundColorAttributeName: NSColor.labelColor(),
			NSFontAttributeName: NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()),
			NSParagraphStyleAttributeName: paragraph,
		})

	@objc.python_method
	def styleEditButton(self, title):
		# The frame hugs the text and its right edge sits on the margin, so
		# the word lands flush no matter how the button aligns its title.
		attributed = self.rightAlignedTitle(title)
		width = int(attributed.size().width) + 6
		self.w.editButton.setPosSize((-(width + MARGIN - 2), -32, width, 18))
		self.w.editButton.getNSButton().setAttributedTitle_(attributed)

	@objc.python_method
	def toggleEditMode(self, sender):
		self.editMode = not self.editMode
		self.styleEditButton("Done" if self.editMode else "Edit")
		self.rebuildList()

	# ------------------------------------------------------------- main list

	@objc.python_method
	def rebuildList(self):
		self._rebuilding = True
		try:
			self._rebuildList()
		finally:
			self._rebuilding = False

	@objc.python_method
	def _rebuildList(self):
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
			# Edit mode shows everything expanded — hiding and reordering
			# need all rows reachable.
			isCollapsed = (category["id"] in collapsed) and not self.editMode
			layout.append((category, catChecks, isCollapsed))
			height += HEADER_HEIGHT
			if not isCollapsed:
				height += len(catChecks) * ROW_HEIGHT
			height += 4
		height += 6

		# Static snapshots of the native disclosure control: identical pixels,
		# but swapping an image is instant — no rotation animation.
		triangleClosed = self.discloseTriangleImage(0)
		triangleOpen = self.discloseTriangleImage(1)

		group = vanilla.Group((0, 0, contentWidth, height))
		y = 6
		for category, catChecks, isCollapsed in layout:
			catId = category["id"]
			safeCat = self.safeAttr(catId)

			if not self.editMode:
				disclose = vanilla.ImageButton(
					(MARGIN - 4, y + 6, 16, 16),
					imageObject=(triangleClosed if isCollapsed else triangleOpen),
					bordered=False,
					callback=lambda sender, cid=catId: self.toggleCollapsed(cid),
				)
				setattr(group, "disclose_%s" % safeCat, disclose)

			if self.editMode:
				# The arrows live in the triangle's slot, narrow enough that
				# the category name keeps its exact position.
				up = vanilla.Button(
					(1, y + 6, 14, 17), "↑", sizeStyle="small",
					callback=lambda sender, cid=catId: self.moveCategory(cid, -1),
				)
				up.getNSButton().setBordered_(False)
				setattr(group, "up_%s" % safeCat, up)
				down = vanilla.Button(
					(15, y + 6, 14, 17), "↓", sizeStyle="small",
					callback=lambda sender, cid=catId: self.moveCategory(cid, 1),
				)
				down.getNSButton().setBordered_(False)
				setattr(group, "down_%s" % safeCat, down)

			label = vanilla.TextBox((MARGIN + 16, y + 5, -150, 17), category["name"])
			setattr(group, "label_%s" % safeCat, label)

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
		# The clip view's frame-change notification fires continuously during
		# live resize — the window's own resize event does not.
		center = NSNotificationCenter.defaultCenter()
		center.removeObserver_name_object_(self, NSVIEW_FRAME_CHANGED, None)
		clipView = nsScrollView.contentView()
		clipView.setPostsFrameChangedNotifications_(True)
		center.addObserver_selector_name_object_(self, "clipFrameChanged:", NSVIEW_FRAME_CHANGED, clipView)
		self.syncContentWidth()
		if scrollY:
			documentView.scrollPoint_((0, scrollY))
		self.updateCounts()

	@objc.python_method
	def syncContentWidth(self, sender=None):
		# Vanilla resets the content group's autoresizing mask, so the group
		# never follows the clip view on its own. Moving the frames directly
		# is reliable: resize the document view AND the group inside it —
		# the row controls have correct masks and shift with their parent.
		if getattr(self, "w", None) is None or not hasattr(self.w, "scroll"):
			return
		try:
			nsScrollView = self.w.scroll.getNSScrollView()
			clipWidth = nsScrollView.contentView().frame().size.width
			documentView = nsScrollView.documentView()
			docSize = documentView.frame().size
			if int(docSize.width) != int(clipWidth):
				documentView.setFrameSize_((clipWidth, docSize.height))
			for subview in documentView.subviews():
				subSize = subview.frame().size
				if int(subSize.width) != int(clipWidth):
					subview.setFrameSize_((clipWidth, subSize.height))
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
			# Nudged left of the checkbox x: the eye image centers in its
			# frame while the checkbox glyph has an internal inset, so this
			# optically aligns the two.
			eyeX = controlX - 3
			eyeImage = self.eyeImage(not isHidden)
			if eyeImage is not None:
				eye = vanilla.ImageButton(
					(eyeX, y + 3, 18, 16), imageObject=eyeImage, bordered=False,
					callback=lambda sender, cid=check["id"]: self.visibilityToggled(cid),
				)
			else:
				eye = vanilla.Button(
					(eyeX, y + 3, 18, 16), "👁" if not isHidden else "–", sizeStyle="small",
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
			if state == STATE_VERIFIED:
				self.tintCheckbox(box, verified=True)
			if font is None:
				box.enable(False)
			setattr(group, "check_%s" % safeCheck, box)
			self.checkboxRefs[check["id"]] = box

		title = check["title"]
		if self.editMode and check.get("custom"):
			title += "  (custom)"
		labelRight = -(MARGIN + 58) if (self.editMode and check.get("custom")) else -40
		label = vanilla.TextBox((titleX, y + 5, labelRight, 16), title, sizeStyle="small")
		if self.editMode and isHidden:
			label.getNSTextField().setTextColor_(NSColor.secondaryLabelColor())
		setattr(group, "title_%s" % safeCheck, label)

		if self.editMode:
			if check.get("custom"):
				removeTitle = self.rightAlignedTitle("Remove")
				removeWidth = int(removeTitle.size().width) + 6
				remove = vanilla.Button(
					(-(removeWidth + MARGIN - 2), y + 4, removeWidth, 17), "Remove", sizeStyle="small",
					callback=lambda sender, cid=check["id"]: self.removeCustomCheck(cid),
				)
				removeNSButton = remove.getNSButton()
				removeNSButton.setBordered_(False)
				removeNSButton.setAttributedTitle_(removeTitle)
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
		self.tintCheckbox(sender, verified=False)
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
	def discloseTriangleImage(self, state):
		"""Snapshot of the native disclosure control in the given state."""
		button = NSButton.alloc().initWithFrame_(((0, 0), (16, 16)))
		button.setTitle_("")
		button.setButtonType_(NS_BUTTON_TYPE_PUSHONPUSHOFF)
		button.setBezelStyle_(NS_BEZEL_DISCLOSURE)
		button.setState_(state)
		rep = button.bitmapImageRepForCachingDisplayInRect_(button.bounds())
		button.cacheDisplayInRect_toBitmapImageRep_(button.bounds(), rep)
		image = NSImage.alloc().initWithSize_((16, 16))
		image.addRepresentation_(rep)
		return image

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
		# Toggle: clicking the ⓘ of the open popover closes it. (On macOS the
		# click that closes a transient popover is swallowed and never reaches
		# the button, so this branch is a safety net — no reopen guard needed,
		# and one would eat the next genuine click.)
		if self.popover is not None and self.popoverCheckId == checkId:
			popover = self.popover
			self.popover = None
			self.popoverCheckId = None
			try:
				popover.close()
			except Exception:
				pass
			return

		check = next((c for c in self.allChecks() if c["id"] == checkId), None)
		if check is None:
			return
		title = check["title"]
		info = check.get("info", "") or "No description yet."
		links = check.get("links", []) or []
		run = check.get("run")

		# One action only for tools: the Open button when the tool is
		# installed, the download link when it is not.
		runAvailable = False
		if run:
			try:
				runAvailable = self.toolAvailable(check)
			except Exception:
				runAvailable = False
		if runAvailable:
			links = []
		# Build checks get a Run Check button when their checker exists.
		checkerName = check.get("checker") if check.get("type") == "build" else None
		checkerAvailable = bool(checkerName) and fec_checkers.has(checkerName)
		actionCount = (1 if runAvailable else 0) + (1 if checkerAvailable else 0)

		# Equal air above and below the body text; when nothing follows the
		# text, the bottom padding matches the side margins instead.
		side = 10
		titleTop, titleHeight, gap = 8, 17, 13
		width = 320
		textHeight = max(34, (len(info) // 46 + info.count("\n") + 1) * 15 + 8)
		bodyTop = titleTop + titleHeight + gap
		buttonCount = actionCount + len(links)
		if buttonCount:
			y = bodyTop + textHeight + gap
			height = y + buttonCount * 24 - 6 + side
		else:
			y = bodyTop + textHeight
			height = y + side

		self.popover = vanilla.Popover((width, height), behavior="transient")
		self.popoverCheckId = checkId
		self.popover.title = vanilla.TextBox((10, titleTop, -10, titleHeight), title)
		self.popover.text = vanilla.TextBox((10, bodyTop, -10, textHeight), info, sizeStyle="small")
		if checkerAvailable:
			self.popover.checkButton = vanilla.Button(
				(10, y, -10, 18), "Run Check", sizeStyle="small",
				callback=lambda sender, c=check: self.runCheckerClicked(c),
			)
			y += 24
		if runAvailable:
			self.popover.runButton = vanilla.Button(
				(10, y, -10, 18), "Open %s" % run.get("label", "tool"), sizeStyle="small",
				callback=lambda sender, c=check: self.runToolClicked(c),
			)
			y += 24
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
		self.popover = None
		self.popoverCheckId = None

	@objc.python_method
	def openURL(self, url):
		NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))

	# ------------------------------------------------------------- checkers

	@objc.python_method
	def runCheckerClicked(self, check):
		font = Glyphs.font
		if font is None:
			Message(title="No font open", message="Open a font first, then run the check.")
			return
		try:
			passed, summary, layers = fec_checkers.run(check["checker"], font)
		except Exception as error:
			Message(title="Checker error", message="%s\n\n%r" % (check["title"], error))
			return
		if passed:
			self.setState(font, check["id"], STATE_VERIFIED)
			box = self.checkboxRefs.get(check["id"])
			if box is not None:
				box.set(True)
				self.tintCheckbox(box, verified=True)
			self.updateCounts()
			if self.popover is not None:
				try:
					self.popover.close()
				except Exception:
					pass
		else:
			if layers:
				tab = font.newTab()
				tab.layers = layers
			Message(title="Check failed", message="%s\n\n%s" % (check["title"], summary))

	@objc.python_method
	def tintCheckbox(self, box, verified):
		# Verified-by-checker ticks are green; manual ticks keep the accent.
		try:
			nsButton = box.getNSButton()
			nsButton.setContentTintColor_(NSColor.systemGreenColor() if verified else None)
		except AttributeError:
			pass

	# ------------------------------------------------------------- tool launch

	@objc.python_method
	def runToolClicked(self, check):
		try:
			opened = self.runTool(check)
		except Exception:
			opened = False
		if opened:
			if self.popover is not None:
				try:
					self.popover.close()
				except Exception:
					pass
		else:
			label = (check.get("run") or {}).get("label", "The tool")
			Message(
				title="%s not found" % label,
				message="%s doesn't seem to be installed. Install it via Window > Plugin Manager, or use the link in this info box." % label,
			)

	@objc.python_method
	def runNeedles(self, check):
		matches = (check.get("run") or {}).get("match", [])
		if isinstance(matches, str):
			matches = [matches]
		return [m.lower().replace(" ", "") for m in matches]

	@objc.python_method
	def findReporter(self, needles):
		for reporter in Glyphs.reporters:
			names = [reporter.__class__.__name__]
			try:
				names.append(str(reporter.title()))
			except Exception:
				pass
			haystack = "".join(names).lower().replace(" ", "")
			if any(needle in haystack for needle in needles):
				return reporter
		return None

	@objc.python_method
	def toolAvailable(self, check):
		"""True when the recommended tool is installed in this Glyphs."""
		run = check.get("run") or {}
		needles = self.runNeedles(check)
		if not needles:
			return False
		if run.get("type") == "reporter":
			return self.findReporter(needles) is not None
		if run.get("type") == "menu":
			return self.findMenuItem(NSApp.mainMenu(), needles) is not None
		return False

	@objc.python_method
	def runTool(self, check):
		"""Opens the recommended tool directly: activates a reporter plugin or
		triggers the script/plugin menu item. Returns False when not installed."""
		run = check.get("run") or {}
		needles = self.runNeedles(check)
		if not needles:
			return False
		if run.get("type") == "reporter":
			reporter = self.findReporter(needles)
			if reporter is None:
				return False
			Glyphs.activateReporter(reporter)
			return True
		if run.get("type") == "menu":
			item = self.findMenuItem(NSApp.mainMenu(), needles)
			if item is None:
				return False
			NSApp.sendAction_to_from_(item.action(), item.target(), item)
			return True
		return False

	@objc.python_method
	def findMenuItem(self, menu, needles):
		for item in menu.itemArray():
			title = str(item.title()).lower().replace(" ", "")
			if item.action() and any(needle in title for needle in needles):
				return item
			if item.hasSubmenu():
				found = self.findMenuItem(item.submenu(), needles)
				if found is not None:
					return found
		return None

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
