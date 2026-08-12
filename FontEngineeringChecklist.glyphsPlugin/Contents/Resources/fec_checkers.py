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
	over = []
	for instance in staticInstances(font):
		try:
			psName = instance.fontName
		except AttributeError:
			psName = "%s-%s" % (
				(font.familyName or "").replace(" ", ""),
				(instance.name or "").replace(" ", ""),
			)
		if len(psName) > 63:
			over.append("%s (%i characters)" % (psName, len(psName)))
	if over:
		return False, "PostScript names over the 63-character limit:\n" + bulletList(over), []
	return True, "All PostScript names stay within 63 characters.", []


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
				outOfSync = (
					layer.leftMetricsKeyOutOfSync()
					or layer.rightMetricsKeyOutOfSync()
					or layer.widthMetricsKeyOutOfSync()
				)
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
	tabularGlyphs = [
		glyph for glyph in font.glyphs
		if glyph.export and (".tf" in glyph.name or ".tosf" in glyph.name)
	]
	if not tabularGlyphs:
		return True, "No tabular glyphs (.tf/.tosf) in the font — nothing to check.", []
	offending = []
	details = []
	for master in font.masters:
		widths = {}
		for glyph in tabularGlyphs:
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
					details.append("%s: %s at %g (majority width %g)" % (master.name, names, width, majority))
	if offending:
		return False, "Tabular widths differ:\n" + bulletList(details), offending
	return True, "All %i tabular glyphs share one width per master." % len(tabularGlyphs), []
