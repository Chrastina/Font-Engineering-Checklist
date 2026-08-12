# encoding: utf-8

"""
Checker functions for the Font Engineering Checklist.

Each checker takes a GSFont and returns a tuple:
    (passed: bool, summary: str, layers: list of GSLayer)

`layers` are the offending layers — the plugin opens them in a new Edit tab
so the user can act on the failure. Empty when the issue is font-level.

Checkers must be deterministic data queries with zero false-positive risk;
anything fuzzier belongs to a recommended tool or the user's eyes.
"""

from __future__ import division, print_function, unicode_literals
import re

from GlyphsApp import Glyphs


CHECKERS = {}


def checker(name):
	def wrap(function):
		CHECKERS[name] = function
		return function
	return wrap


def has(name):
	return name in CHECKERS


def run(name, font):
	function = CHECKERS.get(name)
	if function is None:
		raise ValueError("Checker '%s' is not implemented yet." % name)
	return function(font)


# ------------------------------------------------------------------ helpers

WEIGHT_CLASSES = {
	"thin": 100,
	"extralight": 200, "ultralight": 200,
	"light": 300,
	"regular": 400, "normal": 400,
	"medium": 500,
	"semibold": 600, "demibold": 600,
	"bold": 700,
	"extrabold": 800, "ultrabold": 800,
	"black": 900, "heavy": 900,
}

WIDTH_CLASSES = {
	"ultracondensed": 1,
	"extracondensed": 2,
	"condensed": 3,
	"semicondensed": 4,
	"semiexpanded": 6, "semiextended": 6,
	"expanded": 7, "extended": 7,
	"extraexpanded": 8, "extraextended": 8,
	"ultraexpanded": 9, "ultraextended": 9,
}


def staticInstances(font):
	"""Exporting static instances — variable font settings are skipped."""
	result = []
	for instance in font.instances:
		try:
			if not instance.active:
				continue
		except AttributeError:
			pass
		if getattr(instance, "type", 0) != 0:
			continue
		result.append(instance)
	return result


def bulletList(items, limit=12):
	shown = ["• %s" % item for item in items[:limit]]
	if len(items) > limit:
		shown.append("… and %i more" % (len(items) - limit))
	return "\n".join(shown)


# ----------------------------------------------------------------- checkers

@checker("font_info_complete")
def font_info_complete(font):
	problems = []
	if (font.versionMajor or 0) < 1:
		problems.append("version is %i.%03i — still below 1.000" % (font.versionMajor or 0, font.versionMinor or 0))
	if not (font.designer or "").strip():
		problems.append("designer is empty")
	if not (font.manufacturer or "").strip():
		problems.append("manufacturer is empty")
	if not (font.copyright or "").strip():
		problems.append("copyright is empty")
	licenseValue = None
	try:
		licenseValue = font.license
	except AttributeError:
		try:
			prop = font.propertyForName_("licenses")
			licenseValue = str(prop.value()) if prop else None
		except Exception:
			licenseValue = None
	if not (licenseValue or "").strip():
		problems.append("license is empty")
	if problems:
		return False, "Font info incomplete:\n" + bulletList(problems), []
	return True, "Version, designer, manufacturer, copyright and license are filled in.", []


@checker("ps_name_length")
def ps_name_length(font):
	# 31 characters is the legacy limit this checklist holds names to; 63 is
	# the hard maximum in the specification.
	overHard = []
	overLegacy = []
	for instance in staticInstances(font):
		try:
			psName = instance.fontName
		except AttributeError:
			psName = "%s-%s" % (
				(font.familyName or "").replace(" ", ""),
				(instance.name or "").replace(" ", ""),
			)
		entry = "%s (%i characters)" % (psName, len(psName))
		if len(psName) > 63:
			overHard.append(entry)
		elif len(psName) > 31:
			overLegacy.append(entry)
	if overHard or overLegacy:
		parts = []
		if overHard:
			parts.append("Over the 63-character maximum:\n" + bulletList(overHard))
		if overLegacy:
			parts.append("Over the 31-character legacy limit:\n" + bulletList(overLegacy))
		return False, "\n\n".join(parts), []
	return True, "All PostScript names stay within 31 characters.", []


@checker("weight_width_classes")
def weight_width_classes(font):
	problems = []
	for instance in staticInstances(font):
		name = instance.name or ""
		compact = name.lower().replace(" ", "")

		expected = None
		for token in sorted(WEIGHT_CLASSES, key=len, reverse=True):
			if token in compact:
				expected = (token, WEIGHT_CLASSES[token])
				break
		if expected is not None:
			actual = int(instance.weightClass)
			if actual != expected[1]:
				problems.append("%s: weight class is %i, '%s' suggests %i" % (name, actual, expected[0], expected[1]))

		expected = None
		for token in sorted(WIDTH_CLASSES, key=len, reverse=True):
			if token in compact:
				expected = (token, WIDTH_CLASSES[token])
				break
		if expected is not None:
			actual = int(instance.widthClass)
			if actual != expected[1]:
				problems.append("%s: width class is %i, '%s' suggests %i" % (name, actual, expected[0], expected[1]))
	if problems:
		return False, "Name/class mismatches:\n" + bulletList(problems), []
	return True, "All instance names match their weight and width classes.", []


@checker("vendor_id")
def vendor_id(font):
	value = font.customParameters["vendorID"]
	if not value:
		try:
			prop = font.propertyForName_("vendorID")
			value = prop.value() if prop else None
		except Exception:
			pass
	if not value:
		return False, "No vendorID set. Add the vendorID custom parameter in Font Info > Font.", []
	value = str(value)
	if len(value) != 4 or not all(32 <= ord(character) < 127 for character in value):
		return False, "vendorID is '%s' — it must be exactly 4 ASCII characters." % value, []
	return True, "vendorID is '%s'." % value, []


@checker("metrics_keys_sync")
def metrics_keys_sync(font):
	offending = []
	for glyph in font.glyphs:
		for layer in glyph.layers:
			if not (layer.isMasterLayer or layer.isSpecialLayer):
				continue
			try:
				outOfSync = layer.metricsKeysOutOfSync()
			except AttributeError:
				return False, "This Glyphs version doesn't expose the metrics-key sync state — please report which Glyphs version you're on.", []
			if outOfSync:
				offending.append(layer)
	if offending:
		names = ["%s (%s)" % (layer.parent.name, layer.name) for layer in offending]
		return False, "%i layers have out-of-sync metrics keys:\n%s" % (len(offending), bulletList(names)), offending
	return True, "All metrics keys are in sync.", []


@checker("tabular_widths")
def tabular_widths(font):
	# Group by the full suffix chain: .tf, .tf.sc, .tosf, .tfcentered …
	# each group legitimately has its own tabular width.
	groups = {}
	for glyph in font.glyphs:
		if not glyph.export:
			continue
		parts = glyph.name.split(".")
		if len(parts) < 2:
			continue
		if not any(part.startswith("tf") or part.startswith("tosf") for part in parts[1:]):
			continue
		groups.setdefault(".".join(parts[1:]), []).append(glyph)
	if not groups:
		return True, "No tabular glyphs (.tf/.tosf) in the font — nothing to check.", []
	offending = []
	details = []
	total = 0
	for suffix, glyphs in sorted(groups.items()):
		total += len(glyphs)
		for master in font.masters:
			widths = {}
			for glyph in glyphs:
				layer = glyph.layers[master.id]
				if layer is None:
					continue
				widths.setdefault(round(layer.width, 3), []).append(layer)
			if len(widths) > 1:
				majority = max(widths.items(), key=lambda item: len(item[1]))[0]
				for width, layers in widths.items():
					if width != majority:
						offending.extend(layers)
						names = ", ".join(layer.parent.name for layer in layers)
						details.append("%s, .%s: %s at %g (majority %g)" % (master.name, suffix, names, width, majority))
	if offending:
		return False, "Tabular widths differ within their group:\n" + bulletList(details), offending
	return True, "All %i tabular glyphs share one width per group and master." % total, []


VERTICAL_KEYS = (
	"typoAscender", "typoDescender", "typoLineGap",
	"winAscent", "winDescent",
	"hheaAscender", "hheaDescender", "hheaLineGap",
)


@checker("vf_name_conflict")
def vf_name_conflict(font):
	statics = staticInstances(font)
	variables = []
	for instance in font.instances:
		if getattr(instance, "type", 0) == 0:
			continue
		try:
			if not instance.active:
				continue
		except AttributeError:
			pass
		variables.append(instance)
	if not variables or not statics:
		return True, "Statics and variable fonts don't ship together from this file — no conflict possible.", []
	vfFamilyName = font.customParameters["Variable Font Family Name"]
	if vfFamilyName:
		return True, "Variable Font Family Name parameter is set: '%s'." % vfFamilyName, []
	renamed = [v for v in variables if (v.familyName or "") and v.familyName != font.familyName]
	if len(renamed) == len(variables):
		return True, "All variable font settings carry their own family name.", []
	return False, (
		"Variable font exports share the family name '%s' with the statics — installations collide. "
		"Give the VF its own family name (Variable Font Family Name parameter, or a familyName on the VF setting)."
		% font.familyName
	), []


@checker("notdef_drawn")
def notdef_drawn(font):
	glyph = font.glyphs[".notdef"]
	if glyph is None:
		return False, "There is no .notdef glyph. Glyphs generates a fallback at export — draw your own if it should match the design.", []
	empty = []
	for master in font.masters:
		layer = glyph.layers[master.id]
		if layer is not None and not (layer.paths or layer.components):
			empty.append(layer)
	if empty:
		return False, ".notdef exists but is empty in: %s." % ", ".join(layer.name for layer in empty), empty
	return True, ".notdef is drawn in every master.", []


@checker("contour_directions")
def contour_directions(font):
	offending = []
	for glyph in font.glyphs:
		if not glyph.export:
			continue
		for layer in glyph.layers:
			if not (layer.isMasterLayer or layer.isSpecialLayer):
				continue
			if not layer.paths:
				continue
			copyLayer = layer.copy()
			copyLayer.correctPathDirection()
			# compare direction counts, not order — correcting may reorder paths
			directions = sorted(path.direction for path in layer.paths)
			corrected = sorted(path.direction for path in copyLayer.paths)
			if directions != corrected:
				offending.append(layer)
	if offending:
		names = ["%s (%s)" % (layer.parent.name, layer.name) for layer in offending]
		return False, "%i layers have wrong path directions:\n%s\nPath > Correct Path Direction fixes them." % (len(offending), bulletList(names)), offending
	return True, "All path directions are correct.", []


@checker("uc_diacritics_clipping")
def uc_diacritics_clipping(font):
	offending = []
	details = []
	checkedAny = False
	for master in font.masters:
		top = master.customParameters["winAscent"]
		bottom = master.customParameters["winDescent"]
		if top is None and bottom is None:
			continue
		checkedAny = True
		for glyph in font.glyphs:
			if not glyph.export:
				continue
			layer = glyph.layers[master.id]
			if layer is None:
				continue
			bounds = layer.bounds
			if bounds.size.height == 0:
				continue
			layerTop = bounds.origin.y + bounds.size.height
			layerBottom = bounds.origin.y
			if top is not None and layerTop > float(top):
				offending.append(layer)
				details.append("%s (%s): top %g above winAscent %s" % (glyph.name, master.name, layerTop, top))
			elif bottom is not None and layerBottom < -float(bottom):
				offending.append(layer)
				details.append("%s (%s): bottom %g below winDescent %s" % (glyph.name, master.name, layerBottom, bottom))
	if not checkedAny:
		return True, "No winAscent/winDescent parameters set — Glyphs computes safe values automatically, nothing can clip.", []
	if offending:
		return False, "Glyphs cross the clipping boundary:\n" + bulletList(details), offending
	return True, "Nothing crosses the clipping boundary in any master.", []


@checker("linespacing_across_styles")
def linespacing_across_styles(font):
	# Styles live in masters, in instance-level parameter overrides, and
	# possibly in other open files of the family — compare all of them.
	sources = []
	for openFont in Glyphs.fonts:
		prefix = "" if openFont is font else "%s — " % (openFont.familyName or "?")
		for master in openFont.masters:
			values = dict((key, master.customParameters[key]) for key in VERTICAL_KEYS)
			sources.append(("%s%s" % (prefix, master.name), values))
		for instance in staticInstances(openFont):
			overrides = dict(
				(key, instance.customParameters[key])
				for key in VERTICAL_KEYS
				if instance.customParameters[key] is not None
			)
			if overrides:
				sources.append(("%s%s (instance override)" % (prefix, instance.name or "?"), overrides))
	problems = []
	for key in VERTICAL_KEYS:
		values = {}
		for label, source in sources:
			if key not in source:
				continue
			values.setdefault(str(source[key]), []).append(label)
		if len(values) > 1:
			problems.append("%s: %s" % (key, "; ".join(
				"%s (%s)" % (value, ", ".join(labels[:4])) for value, labels in values.items())))
	if problems:
		return False, "Line spacing is inconsistent across styles:\n" + bulletList(problems), []
	if len(Glyphs.fonts) > 1:
		scope = "%i open fonts" % len(Glyphs.fonts)
	else:
		scope = "%i masters" % len(font.masters)
	return True, "Vertical metrics agree across %s and all instance overrides." % scope, []


@checker("anchor_consistency")
def anchor_consistency(font):
	# Only anchors that a mark in this font actually attaches to are
	# required — GlyphData also lists anchors (like 'center') that most
	# designs never use.
	attachmentNames = set()
	masterId = font.masters[0].id
	for glyph in font.glyphs:
		layer = glyph.layers[masterId]
		if layer is None:
			continue
		for anchor in layer.anchors:
			name = str(anchor.name)
			if name.startswith("_"):
				attachmentNames.add(name[1:].split("@")[0])
	if not attachmentNames:
		return True, "No combining marks with attachment anchors in the font — nothing to enforce.", []
	offending = []
	details = []
	for glyph in font.glyphs:
		if not glyph.export:
			continue
		info = glyph.glyphInfo
		expected = list(info.anchors) if (info and info.anchors) else None
		if not expected:
			continue
		# GlyphData may carry position specs ('top@x*0.5') — names only.
		expected = [str(name).split("@")[0] for name in expected]
		expected = [name for name in expected if name in attachmentNames]
		if not expected:
			continue
		for layer in glyph.layers:
			if not layer.isMasterLayer:
				continue
			if layer.components and not layer.paths:
				continue  # composites inherit anchors from their components
			present = set(str(anchor.name).split("@")[0] for anchor in layer.anchors)
			missing = [name for name in expected if name not in present]
			if missing:
				offending.append(layer)
				details.append("%s (%s): missing %s" % (glyph.name, layer.name, ", ".join(missing)))
	if offending:
		return False, "Layers missing expected anchors:\n" + bulletList(details), offending
	return True, "All glyphs carry the anchors Glyphs expects.", []


LIGATURE_FEATURES = ("liga", "dlig", "rlig", "clig", "hlig")


@checker("ligature_carets")
def ligature_carets(font):
	# Only glyphs actually produced by a ligature feature need carets.
	targets = set()
	for feature in font.features:
		if str(feature.name) not in LIGATURE_FEATURES:
			continue
		code = feature.code or ""
		for match in re.finditer(r"\bby\s+([A-Za-z0-9_.]+)\s*;", code):
			targets.add(match.group(1))
	if not targets:
		return True, "No ligature substitutions found in %s — nothing needs carets." % "/".join(LIGATURE_FEATURES), []
	offending = []
	details = []
	for name in sorted(targets):
		glyph = font.glyphs[name]
		if glyph is None or not glyph.export:
			continue
		base = glyph.name.split(".")[0]
		parts = [part for part in base.split("_") if part]
		needed = len(parts) - 1 if len(parts) >= 2 else 1
		for layer in glyph.layers:
			if not layer.isMasterLayer:
				continue
			carets = [anchor for anchor in layer.anchors if str(anchor.name).startswith("caret")]
			if len(carets) < needed:
				offending.append(layer)
				details.append("%s (%s): %i of %i caret anchors" % (glyph.name, layer.name, len(carets), needed))
	if offending:
		return False, "Ligatures missing caret anchors:\n" + bulletList(details), offending
	return True, "All %i ligature glyphs carry their caret anchors." % len(targets), []


@checker("ss_named")
def ss_named(font):
	ssFeatures = [feature for feature in font.features if re.match(r"ss\d\d$", str(feature.name))]
	if not ssFeatures:
		return True, "No stylistic sets in the font — nothing to name.", []
	unnamed = []
	for feature in ssFeatures:
		labeled = False
		try:
			if feature.labels:
				labeled = True
		except AttributeError:
			pass
		if not labeled and "Name:" in (feature.notes or ""):
			labeled = True
		if not labeled:
			unnamed.append(str(feature.name))
	if unnamed:
		return False, "Stylistic sets without a name: %s. Add names in Font Info > Features." % ", ".join(unnamed), []
	return True, "All %i stylistic sets are named." % len(ssFeatures), []


@checker("ss_coverage")
def ss_coverage(font):
	names = set(glyph.name for glyph in font.glyphs)
	suffixes = sorted(set(
		match.group(1) for name in names
		for match in [re.search(r"\.(ss\d\d)$", name)] if match
	))
	if not suffixes:
		return True, "No .ssXX glyphs in the font — nothing to cover.", []
	missing = []
	layers = []
	masterId = font.masters[0].id
	for suffix in suffixes:
		bases = set(name[:-(len(suffix) + 1)] for name in names if name.endswith("." + suffix))
		for glyph in font.glyphs:
			# Only plain composites: a glyph that already carries a suffix
			# (.ssXX, .sc, .locl…) follows its own naming logic.
			if not glyph.export or "." in glyph.name:
				continue
			layer = glyph.layers[masterId]
			if layer is None or not layer.components:
				continue
			usedBases = [
				c.componentName for c in layer.components
				if c.componentName in bases and not str(c.componentName).startswith("_")
			]
			if usedBases and ("%s.%s" % (glyph.name, suffix)) not in names:
				missing.append("%s.%s (uses %s)" % (glyph.name, suffix, ", ".join(usedBases)))
				layers.append(layer)
	if missing:
		return False, "Report — composites whose base has a stylistic variant but which lack their own:\n" + bulletList(missing), layers
	return True, "Stylistic sets cover all related composites.", []


@checker("use_typo_metrics")
def use_typo_metrics(font):
	value = font.customParameters["Use Typo Metrics"]
	if value is None:
		value = font.customParameters["useTypoMetrics"]
	if not value:
		return False, "The 'Use Typo Metrics' parameter isn't set. Add it in Font Info > Font so apps use the typo metrics for line spacing.", []
	missing = []
	for master in font.masters:
		for key in ("typoAscender", "typoDescender"):
			if master.customParameters[key] is None:
				missing.append("%s: %s" % (master.name, key))
	if missing:
		return False, (
			"'Use Typo Metrics' is set, but the typo metrics apps will now rely on are empty:\n"
			+ bulletList(missing)
		), []
	return True, "'Use Typo Metrics' is set and the typo metrics are defined.", []


@checker("style_linking")
def style_linking(font):
	instances = staticInstances(font)
	byName = dict((str(instance.name or ""), instance) for instance in instances)
	problems = []
	linkedAny = False
	for instance in instances:
		name = str(instance.name or "")
		compact = name.lower().replace(" ", "")
		isBold = "bold" in compact and "semibold" not in compact and "extrabold" not in compact and "ultrabold" not in compact
		isItalic = bool(getattr(instance, "isItalic", False)) or "italic" in compact or "oblique" in compact
		if not (isBold or isItalic):
			continue
		linkName = str(getattr(instance, "linkStyle", "") or "")
		if not linkName:
			problems.append("%s: no linked style set (Font Info > Exports > Style Linking)" % name)
			continue
		linkedAny = True
		if linkName not in byName:
			problems.append("%s: linked to '%s', which is not an exporting instance" % (name, linkName))
	if problems:
		return False, "Style linking problems:\n" + bulletList(problems), []
	if not linkedAny:
		return True, "No bold or italic instances that need style linking.", []
	return True, "Bold and italic instances are linked to existing base styles.", []


@checker("master_locations")
def master_locations(font):
	if not font.masters:
		return False, "The font has no masters.", []
	problems = []
	seen = {}
	for master in font.masters:
		try:
			coordinates = tuple(round(float(value), 3) for value in master.axes)
		except (AttributeError, TypeError):
			continue
		if coordinates in seen:
			problems.append("%s and %s sit at the same location %s" % (seen[coordinates], master.name, list(coordinates)))
		seen[coordinates] = master.name
	axisCount = len(font.axes) if font.axes else 0
	for index in range(axisCount):
		values = set()
		for master in font.masters:
			try:
				values.add(round(float(master.axes[index]), 3))
			except (AttributeError, IndexError, TypeError):
				pass
		if len(values) < 2:
			problems.append("axis '%s' has masters at only one location — it cannot interpolate" % font.axes[index].name)
			continue
		low, high = min(values), max(values)
		for instance in staticInstances(font):
			try:
				position = round(float(instance.axes[index]), 3)
			except (AttributeError, IndexError, TypeError):
				continue
			if position < low or position > high:
				problems.append("instance '%s' at %g is outside the masters' %s range (%g–%g)" % (
					instance.name, position, font.axes[index].name, low, high))
	if problems:
		return False, "Designspace problems:\n" + bulletList(problems), []
	return True, "Masters sit at distinct locations and every instance falls inside the designspace.", []


@checker("default_master")
def default_master(font):
	origin = font.customParameters["Variable Font Origin"]
	if origin:
		for master in font.masters:
			if master.id == origin or master.name == str(origin):
				return True, "Variable Font Origin is '%s' — confirm this is the intended default." % master.name, []
		return False, "Variable Font Origin points at '%s', which is not one of the masters." % origin, []
	first = font.masters[0]
	return True, (
		"No Variable Font Origin parameter, so the default is the first master: '%s'.\n"
		"Confirm that is the style apps should show before any axis is touched."
		% first.name
	), []


SPACE_GLYPHS = (
	"nbspace", "figurespace", "thinspace", "hairspace",
	"emspace", "enspace", "punctuationspace", "zerowidthspace",
)


@checker("space_glyphs")
def space_glyphs(font):
	missing = [name for name in SPACE_GLYPHS if font.glyphs[name] is None]
	if missing:
		return False, (
			"Space characters not in the font:\n%s\n\n"
			"Build Space Glyphs (mekkablue scripts) adds them with correct, metrics-keyed widths."
			% bulletList(missing)
		), []
	return True, "All the usual space characters are present.", []


@checker("empty_glyphs")
def empty_glyphs(font):
	offending = []
	names = []
	for glyph in font.glyphs:
		if not glyph.export or glyph.category == "Separator":
			continue
		for layer in glyph.layers:
			if not layer.isMasterLayer:
				continue
			if not layer.paths and not layer.components and layer.width == 0:
				offending.append(layer)
				names.append("%s (%s)" % (glyph.name, layer.name))
	if offending:
		return False, "Exporting glyphs that are completely empty:\n" + bulletList(names), offending
	return True, "No empty exporting glyphs.", []


@checker("missing_unicodes")
def missing_unicodes(font):
	missing = []
	layers = []
	masterId = font.masters[0].id
	for glyph in font.glyphs:
		if not glyph.export or glyph.unicode:
			continue
		info = glyph.glyphInfo
		expected = getattr(info, "unicode", None) if info else None
		if expected:
			missing.append("%s (expected U+%s)" % (glyph.name, expected))
			layer = glyph.layers[masterId]
			if layer is not None:
				layers.append(layer)
	if missing:
		return False, "Exporting glyphs without their expected Unicode value:\n" + bulletList(missing), layers
	return True, "Every exporting glyph that should have a Unicode value has one.", []


@checker("duplicate_unicodes")
def duplicate_unicodes(font):
	seen = {}
	for glyph in font.glyphs:
		if not glyph.export or not glyph.unicode:
			continue
		seen.setdefault(str(glyph.unicode), []).append(glyph.name)
	clashes = ["U+%s: %s" % (code, ", ".join(names)) for code, names in sorted(seen.items()) if len(names) > 1]
	if clashes:
		return False, "Several glyphs claim the same Unicode value:\n" + bulletList(clashes), []
	return True, "No duplicate Unicode values.", []


@checker("feature_code_compiles")
def feature_code_compiles(font):
	try:
		font.compileFeatures()
	except Exception as error:
		return False, "Feature compilation failed:\n%s" % error, []
	problems = []
	for collection, label in ((font.features, "feature"), (font.featurePrefixes, "prefix"), (font.classes, "class")):
		for item in collection:
			try:
				error = item.error
			except AttributeError:
				error = None
			if error:
				problems.append("%s %s: %s" % (label, item.name, str(error).strip()))
	if problems:
		return False, "Feature code has errors:\n" + bulletList(problems), []
	return True, "All feature code, prefixes and classes compile without errors.", []


@checker("brace_layers_in_designspace")
def brace_layers_in_designspace(font):
	if not font.axes:
		return True, "The font has no axes — nothing to validate.", []
	ranges = []
	for index in range(len(font.axes)):
		values = []
		for master in font.masters:
			try:
				values.append(float(master.axes[index]))
			except (AttributeError, IndexError, TypeError):
				pass
		ranges.append((min(values), max(values)) if values else (None, None))
	problems = []
	offending = []
	for glyph in font.glyphs:
		if not glyph.export:
			continue
		for layer in glyph.layers:
			if not layer.isSpecialLayer or not layer.attributes:
				continue
			coordinates = layer.attributes.get("coordinates")
			if not coordinates:
				continue
			try:
				values = [float(value) for value in list(coordinates.values())]
			except (AttributeError, TypeError, ValueError):
				continue
			for index, value in enumerate(values):
				if index >= len(ranges):
					continue
				low, high = ranges[index]
				if low is None:
					continue
				if value < low or value > high:
					problems.append("%s (%s): %s at %g is outside %g–%g" % (
						glyph.name, layer.name, font.axes[index].name, value, low, high))
					offending.append(layer)
	if problems:
		return False, (
			"Brace layers outside the designspace (they silently do nothing):\n" + bulletList(problems)
		), offending
	return True, "All brace layer coordinates sit inside the designspace.", []


SC_SUFFIXES = (".sc", ".smcp", ".c2sc")


@checker("smallcaps_coverage")
def smallcaps_coverage(font):
	names = set(glyph.name for glyph in font.glyphs)
	scSuffix = None
	for suffix in SC_SUFFIXES:
		if any(name.endswith(suffix) for name in names):
			scSuffix = suffix
			break
	if scSuffix is None:
		return True, "No small cap glyphs in the font — nothing to cover.", []
	missing = []
	layers = []
	masterId = font.masters[0].id
	for glyph in font.glyphs:
		# Letters only — roman numerals and other uppercase symbols don't
		# take small cap forms.
		if not glyph.export or not glyph.unicode or glyph.category != "Letter":
			continue
		try:
			character = glyph.string
		except AttributeError:
			character = None
		if not character or len(character) != 1 or not character.isupper():
			continue
		candidates = ["%s%s" % (glyph.name, scSuffix)]
		lowered = character.lower()
		if len(lowered) == 1:
			lowerGlyph = font.glyphs[lowered]
			if lowerGlyph is not None:
				candidates.append("%s%s" % (lowerGlyph.name, scSuffix))
		if not any(candidate in names for candidate in candidates):
			missing.append("%s (expected %s)" % (glyph.name, " or ".join(candidates)))
			layer = glyph.layers[masterId]
			if layer is not None:
				layers.append(layer)
	if missing:
		return False, "Uppercase without small cap counterparts:\n" + bulletList(missing), layers
	return True, "Every uppercase character has a small cap counterpart.", []
