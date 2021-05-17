# Parse Borderlands 2 savefiles and list all items across all characters
# See https://github.com/gibbed/Gibbed.Borderlands2 for a Windows-only
# program to do way more than this, including actually changing stuff.
# This is much simpler; its purpose is to help you twink items between
# your characters, or more specifically, to find the items that you want
# to twink. It should be able to handle Windows and Linux save files, but
# not save files from consoles (they may be big-endian, and/or use another
# compression algorithm). Currently the path is hard-coded for Linux though.
import argparse
import base64
import binascii
import collections
import hashlib
import itertools
import json
import math
import os.path
import struct
import sys
import random
from fnmatch import fnmatch
from dataclasses import dataclass # ImportError? Upgrade to Python 3.7 or pip install dataclasses
from pprint import pprint
import lzo # ImportError? pip install python-lzo (or downgrade to Python 3.9 possibly)
from BL1_find_items import FunctionArg, Consumable

# python-lzo 1.12 on Python 3.8 causes a DeprecationWarning regarding arg parsing with integers.
import warnings; warnings.filterwarnings("ignore")

loot_filter = FunctionArg("filter", 1)

@loot_filter
def level(item, minlvl, maxlvl=None):
	minlvl = int(minlvl)
	if maxlvl is None: maxlvl = minlvl + 5
	return minlvl <= item.grade <= int(maxlvl)

@loot_filter
def type(item, type): return type in item.type
del type # I want the filter to be called type, but not to override type()

@loot_filter
def title(item, tit): return item.title is not None and tit in item.title


synthesizer = FunctionArg("synth", 1)

def strip_prefix(str): return str.split(".", 1)[1]
def armor_serial(serial): return base64.b64encode(serial).decode("ascii").strip("=")
def unarmor_serial(id): return base64.b64decode(id.strip("{}").encode("ascii") + b"====")

@synthesizer
def money(savefile): savefile.money[0] += 5000000 # Add more dollars
@synthesizer
def eridium(savefile): savefile.money[1] += 500 # Add more eridium/moonstones

@synthesizer
def xp(savefile, xp=None):
	# Change the experience point count, without going beyond the level.
	min = math.ceil(60 * savefile.level ** 2.8 - 60)
	max = math.ceil(60 * (savefile.level + 1) ** 2.8 - 60) - 1
	if xp is None: savefile.exp = max
	elif min <= int(xp) <= max: savefile.exp = int(xp)
	else: print("WARNING: Leaving XP unchanged - level %d needs %d-%d XP" % (savefile.level, min, max))

@synthesizer
def boost(savefile):
	"""Boost the levels of all equipped gear lower than your current level"""
	for i, weapon in enumerate(savefile.packed_weapon_data):
		weap = Asset.decode_asset_library(weapon.serial)
		if weap.grade < savefile.level and weapon.quickslot:
			weap.grade = weap.stage = savefile.level
			savefile.packed_weapon_data[i].serial = weap.encode_asset_library()
	for i, item in enumerate(savefile.packed_item_data):
		it = Asset.decode_asset_library(item.serial)
		if it and it.grade < savefile.level and item.equipped:
			it.grade = it.stage = savefile.level
			savefile.packed_item_data[i].serial = it.encode_asset_library()

@synthesizer
def invdup(savefile, level):
	"""Duplicate inventory at a new level for comparison"""
	levels = [int(l) for l in level.split(",") if l]
	if not levels: raise ValueError("C'mon, get on my level, man")
	for weapon in savefile.packed_weapon_data:
		weap = Asset.decode_asset_library(weapon.serial)
		if weap.grade not in levels and not weapon.quickslot:
			for level in levels:
				weap.grade = weap.stage = level
				weap.seed = random.randrange(1<<31)
				packed = PackedWeaponData(serial=weap.encode_asset_library(), quickslot=0, mark=1, unknown4=0)
				savefile.packed_weapon_data.append(packed)
	for item in savefile.packed_item_data:
		it = Asset.decode_asset_library(item.serial)
		if it and it.grade not in levels and not item.equipped:
			for level in levels:
				it.grade = it.stage = level
				it.seed = random.randrange(1<<31)
				packed = PackedItemData(serial=it.encode_asset_library(), quantity=1, equipped=0, mark=1)
				savefile.packed_item_data.append(packed)

@synthesizer
def create_many(savefile):
	"""Synthesize a bunch of similar items for comparison"""
	# for part in get_asset("Item Types")["GD_ClassMods.A_Item_Siren.ClassMod_Siren_Binder"]["alpha_parts"]:
	for lvl in sorted(random.sample(range(12, 73), 10), reverse=True):
		if GAME == "borderlands the pre-sequel":
			# Create purple "Loot Pinata" class mod
			setid = 0
			cats = ('GD_Cork_ClassMods', 'GD_Cork_ItemGrades', 'GD_Weap_Shared_Names',)
			type = "A_Item_Prototype.ClassMod_Prototype_Pinata"
			balance = "ClassMods.BalDef_ClassMod_Prototype_04_VeryRare"
			alpha = "Specialization.Spec_AS1_BS2_CS3"
			pfx = "Prefix_Prototype.Prefix_Pinata_01_Loot"
			brand = "Manufacturers.Bandit"
		elif lvl > 25:
			# Create "Legendary Binder" class mod
			setid = 10
			cats = ("GD_Lobelia_ClassMods", "GD_ClassMods",)
			type = "A_Item_Siren.ClassMod_Siren_LegendaryBinder"
			balance = "ClassMods.BalDef_ClassMod_Lobelia_Siren_05_Legendary"
			alpha = "Specialization.Spec_Legendary"
			pfx = "Prefix_Siren.Prefix_LegendaryBinder"
			brand = "Manufacturers.Maliwan"
		else:
			# Create purple "Chrono Binder" class mod
			setid = 0
			cats = ("GD_ClassMods",)
			type = "A_Item_Siren.ClassMod_Siren_Binder"
			balance = "ClassMods.BalDef_ClassMod_Siren_04_VeryRare"
			alpha = "Specialization.Spec_AS3_BS1_CS2"
			pfx = "Prefix_Siren.Prefix_Binder_03_ChronoBinder"
			brand = "Manufacturers.Maliwan"
		synth = Asset(seed=random.randrange(1<<31), is_weapon=0, setid=setid, categories=cats, type=type, balance=balance,
			brand=brand, grade=lvl, stage=lvl,
			pieces=[alpha, "StatPrimary.PrimaryStat_A5_B0_C0",
				"StatPrimary02.PrimaryStat02_A0_B5_C0", None, None, None, None, None],
			material="StatPenalty.StatPenalty_A0_B0_C2",
			pfx=pfx, title="Title.Title_ClassMod",
		)
		packed = PackedItemData(serial=synth.encode_asset_library(), quantity=1, equipped=0, mark=1)
		savefile.packed_item_data.append(packed)

@synthesizer
def create_item(savefile):
	synth = Asset(seed=random.randrange(1<<31), is_weapon=0, setid=0, categories=("GD_ClassMods",),
		type="A_Item_Merc.ClassMod_Merc_Hoarder", balance="ClassMods.BalDef_ClassMod_Mercenary_04_VeryRare",
		brand="Manufacturers.Vladof", grade=33, stage=33,
		pieces=["Specialization.Spec_AS2_BS1_CS3", "StatPrimary.PrimaryStat_A5_B0_C0",
			"StatPrimary02.PrimaryStat02_A0_B5_C0", None, None, None, None, None],
		material="StatPenalty.StatPenalty_A0_B0_C2",
		pfx="Prefix_Merc.Prefix_Hoarder_02_LuckyHoarder", title="Title.Title_ClassMod",
	)
	# or:
	synth = Asset(seed=random.randrange(1<<31), is_weapon=0, setid=0, categories=("GD_Shields",),
		type="A_Item.Shield_Absorption_05_LegendaryShock", balance="Shields.ItemGrade_Gear_Shield_Absorption_05_LegendaryShock",
		brand="Manufacturers.Vladof", grade=30, stage=30,
		pieces=["Body.Body8_Pangolin", "Battery.Battery8_Pangolin",
			"Capacitor.Capacitor5_Maliwan_ShockRes_Legendary",
			"Accessory.Accessory3_Absorption_LegendaryShock",
			None, None, None, None],
		material="Material.Material5_Legendary_AbsorptionShock",
		pfx="Prefixes.Prefix_Capacity_Pangolin05", title="Titles.Title_Shield",
	)
	packed = PackedItemData(serial=synth.encode_asset_library(), quantity=1, equipped=0, mark=1)
	savefile.packed_item_data.append(packed)

@synthesizer
def create_weap(savefile):
	synth = Asset(seed=random.randrange(1<<31), is_weapon=1, setid=0, categories=('GD_Weap_Shotgun', 'GD_Weap_Shotgun', 'GD_Weap_Shared_Names'), type='A_Weapons.WT_Jakobs_Shotgun', balance='A_Weapons.SG_Jakobs_4_VeryRare', brand='Manufacturers.Jakobs', grade=22, stage=22, pieces=['Body.SG_Body_Jakobs_5', 'Grip.SG_Grip_Tediore', 'Barrel.SG_Barrel_Bandit', 'Sight.SG_Sight_Jakobs', 'Stock.SG_Stock_Hyperion', None, 'Accessory.SG_Accessory_VerticalGrip', None], material='ManufacturerMaterials.Mat_Jakobs_5', pfx='Name.Prefix_Jakobs.Prefix_VerticalGrip_Stability', title='Name.Title_Jakobs.Title_Barrel_Bandit_TripleBarrel'
	)
	packed = PackedWeaponData(serial=synth.encode_asset_library(), quickslot=0, mark=1, unknown4=0)
	savefile.packed_weapon_data.append(packed)

# Asset(seed=874029394, is_weapon=False, setid=0, categories=('GD_Shields', 'GD_ItemGrades', 'GD_Weap_Shared_Names'), type='A_Item.Shield_Juggernaut', balance='Shields.ItemGrade_Gear_Shield_Juggernaut_04_VeryRare', brand='Manufacturers.Pangolin', grade=44, stage=44, pieces=['Body.Body5_Anshin', 'Battery.Battery1_Tediore', 'Capacitor.Capacitor5_Anshin', 'Accessory.Accessory8_Juggernaut', None, None, None, None], material='Material.Material4_VeryRare_Juggernaut', pfx='Prefixes.Prefix_Special_Pangolin05', title='Titles.Title_Juggernaut01_JuggernautShield')

@synthesizer
def create_all_items(savefile):
	"""Synthesize every possible item based on its Balance definition"""
	if GAME == "borderlands the pre-sequel":
		balance = "GD_Cork_GrenadeMods.A_Item_Legendary.GM_BonusPackage"
		setid = 0
		cats = ('GD_Cork_GrenadeMods', 'GD_GrenadeMods', 'GD_Weap_Shared_Names')
		level = 25
		pfx, title = 'Prefix.Prefix_Longbow', "Title.Title_BonusPackage"
		pieces = [..., 'Delivery.Delivery_LongBow', 'Trigger.Trigger_Grade0', ..., 'Damage.Damage_Grade7',
			'DamageRadius.DamageRadius_ExtraLarge', 'ChildCount.ChildCount_Grade6', ...]
	else:
		balance = "GD_Aster_GrenadeMods.A_Item.GM_ChainLightning"
		setid = 9
		cats = ('GD_Aster_GrenadeMods', 'GD_GrenadeMods', 'GD_Weap_Shared_Names') # NOT the same as a normal Chain Lightning gives. Hmm.
		level = 35
		pfx, title = None, "Title.Title_ChainLightning"
		pieces = [...] * 8
	# Below shouldn't need to be changed.
	bal = get_asset("Item Balance")[balance]
	balance = strip_prefix(balance)
	type = strip_prefix(bal["type"])
	p = bal["parts"]
	pieces = [p.get(c, [None]) if pp is ... else ["." + pp]
		for c, pp in zip(["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"], pieces)]
	for mfg, mat, *pieces in itertools.product(bal["manufacturers"], p["material"], *pieces):
		synth = Asset(seed=random.randrange(1<<31), is_weapon=0, setid=setid, categories=cats,
			type=type, balance=balance, brand=strip_prefix(mfg), grade=level, stage=level,
			pieces=[piece and strip_prefix(piece) for piece in pieces],
			material=strip_prefix(mat), pfx=pfx, title=title,
		)
		packed = PackedItemData(serial=synth.encode_asset_library(), quantity=1, equipped=0, mark=1)
		savefile.packed_item_data.append(packed)

@synthesizer
def create_all_weapons(savefile):
	"""Synthesize every possible weapon based on its Balance definition"""
	# Random note: Glitch attachments that begin with 0 are identified correctly
	# eg GD_Ma_Weapons.Glitch_Attachments.Glitch_Attachment_0421 gives O0L4M2A1.
	# Other attachments have the internal name give an Amplify value higher by one
	# eg GD_Ma_Weapons.Glitch_Attachments.Glitch_Attachment_2144 is O2L1M4A3. Odd.
	balance = "GD_Ma_Weapons.A_Weapons.SMG_Dahl_6_Glitch"
	setid = 5
	cats = ('GD_Weap_SMG', 'GD_Ma_Weapons', 'GD_Weap_Shared_Names')
	level = 26
	pfx, title = 'Name.Prefix_Dahl.Prefix_Body1_Accurate', 'Name.Title_Dahl.Title_Barrel_Dahl_Stable'
	bal = get_asset("Weapon Balance")[balance]
	balance = strip_prefix(balance)
	type = strip_prefix(bal.get("type", "GD_Weap_SMG.A_Weapons.WT_SMG_Dahl"))
	mfg = "Manufacturers.Dahl"
	mat = strip_prefix(bal["parts"]["material"][0])
	pieces = ['Body.SMG_Body_Dahl_VarC', 'Grip.SMG_Grip_Maliwan', 'Barrel.SMG_Barrel_Dahl', 'Sight.SMG_Sight_Dahl',
		'Stock.SMG_Stock_Hyperion', 'elemental.SMG_Elemental_Corrosive', 'Accessory.SMG_Accessory_Body1_Accurate', ...]
	for piece in bal["parts"]["accessory2"]:
		pieces[7] = strip_prefix(piece)
		synth = Asset(seed=random.randrange(1<<31), is_weapon=1, setid=setid, categories=cats,
			type=type, balance=balance, brand=mfg, grade=level, stage=level,
			pieces=pieces, material=mat, pfx=pfx, title=title,
		)
		print("Creating:", synth)
		packed = PackedWeaponData(serial=synth.encode_asset_library(), quickslot=0, mark=1, unknown4=0)
		savefile.packed_weapon_data.append(packed)

@synthesizer
def give(savefile, definitions):
	"""Synthesize every part variant (only parts) based on a particular item/weapon"""
	for definition in definitions.split(","):
		[id, *changes] = definition.split("-")
		serial = unarmor_id(id)
		obj = Asset.decode_asset_library(serial)
		obj.seed = random.randrange(1<<31) # If any changes are made, rerandomize the seed too
		for change in changes:
			if not change: continue
			c = change[0].lower()
			if c == "l": obj.grade = obj.stage = int(change[1:])
			# TODO: Add other changes as needed
		if changes: serial = obj.encode_asset_library()
		if obj.is_weapon: savefile.packed_weapon_data.append(PackedWeaponData(serial=serial, quickslot=0, mark=1, unknown4=0))
		else: savefile.packed_item_data.append(PackedItemData(serial=serial, quantity=1, equipped=0, mark=1))

@synthesizer
def crossproduct(savefile, baseid):
	obj = Asset.decode_asset_library(unarmor_serial(baseid))
	cls = "Weapon" if obj.is_weapon else "Item"
	print()
	print("Basis:", obj)
	allbal = get_asset(cls + " Balance")
	for cat in obj.categories:
		try:
			bal = allbal[cat + "." + obj.balance]
			break
		except KeyError: pass
	else:
		raise Exception("couldn't find balance") # shouldn't happen, will be ugly
	# Build up a full list of available parts
	# Assumes that the "mode" is always "Selective" as I don't know how "Additive works exactly
	checkme = cat + "." + obj.balance
	partnames = ("body grip barrel sight stock elemental acc1 acc2" if obj.is_weapon else "alpha beta gamma delta epsilon zeta eta theta").split()
	pieces = [None] * len(partnames)
	while checkme:
		parts = allbal[checkme]["parts"]
		pieces = [p or parts.get(part) for p, part in zip(pieces, partnames)]
		checkme = allbal[checkme].get("base")
	pieces = [p or [None] for p in pieces] # Any still unfound, just leave None in them
	for pieces in itertools.product(*pieces):
		obj.seed = random.randrange(1<<31)
		obj.grade = obj.stage = 41
		obj.pieces = [piece and strip_prefix(piece) for piece in pieces]
		print(obj)
		if obj.is_weapon:
			packed = PackedWeaponData(serial=obj.encode_asset_library(), quickslot=0, mark=1, unknown4=0)
			savefile.packed_weapon_data.append(packed)
		else:
			packed = PackedItemData(serial=obj.encode_asset_library(), quantity=1, equipped=0, mark=1)
			savefile.packed_item_data.append(packed)

parser = argparse.ArgumentParser(description="Borderlands 2/Pre-Sequel save file reader")
parser.add_argument("-2", "--bl2", help="Read Borderlands 2 savefiles",
	action="store_const", const="borderlands 2", dest="game")
parser.add_argument("-p", "--tps", help="Read Borderlands The Pre-Sequel savefiles",
	action="store_const", const="borderlands the pre-sequel", dest="game")
parser.set_defaults(game="borderlands 2")
parser.add_argument("--proton", help="Read savefiles from Proton installation",
	action="store_const", const="proton", dest="platform")
parser.add_argument("--native", help="Read savefiles from native Linux installation",
	action="store_const", const="native", dest="platform")
parser.set_defaults(platform="native")
parser.add_argument("--player", help="Choose which player (by Steam ID) to view savefiles of")
parser.add_argument("--verify", help="Verify code internals by attempting to back-encode", action="store_true")
parser.add_argument("--pieces", help="Show the individual pieces inside weapons/items", action="store_true")
parser.add_argument("--raw", help="Show the raw details of weapons/items (spammy - use loot filters)", action="store_true")
parser.add_argument("--itemids", help="Show the IDs of weapons/items", action="store_true")
parser.add_argument("--synth", help="Synthesize a modified save file", type=synthesizer, nargs="*")
parser.add_argument("-l", "--loot-filter", help="Show loot, optionally filtered to only what's interesting", type=loot_filter, nargs="*")
parser.add_argument("-f", "--file", help="Process only one save file")
parser.add_argument("--library", help="Add an item ID to the library")
args = parser.parse_args()
print(args)

GAME = args.game

# Library of item IDs. Everything here is seed=grade=stage=50 for consistency.
# TODO: Have an easy way to pick and choose, and have them set to the player's level (and randomize the seed)
# TODO: Check variants of each of these and pick out the best. The "# V" tag means I haven't checked variants.
library = {
	"*": {
		# Good for anyone
		"hwAAADLKv4T3Nj+nwWj5D93eEsI037K1X4yK8cYDK8sWhOzS7cRJ": "Lucid Florentine", # V
		"hwAAADIKvoT3NjynwWgFbZDeYkkhn4u8XMwIu9UDK6MWhOxyZrFJ": "Bulets Go Fasterifed Slagga", # Florentine and Slagga are both slag-em-up SMGs
		"hwAAADKKvoT5NjunwWhxDgXdssM0KLK9XOwK+tQDK6MWrOwC7KRJ": "Bladed Tattler", # V
		"hwAAADIHS+32Aj7PwWjhy0mUAdMnG2S8mOMOut0DK4+3zajR/ZdJ": "Rapid Infinity", # V
		"hwAAADLClhT5FjHnwWg5bene4E4lbRm8nSIJxdMDKw8WpengZrVJ": "Onslaught Veruc", # V
		"hwAAADKKvgT4Nj+nwWiJr9XeckI2scu4XoyK89oDK8MWrOyybQZI": "Corporate Yellow Jacket", # V
		"BwAAADI+S20AZS3fO3dt34kdgMHMtQqOBQUK/BfdR5k": "Skin of the Ancients", # V
		"BwAAADICsRH5mSU8wOjSjJ4fogH5Ohu+EzziescQoXq3uy5RbvU": "Sticky Lobbed Bonus Package", # V. Want a longbow probably, short fuse.
		"BwAAADLCshH5WSU8wOjSzIkfogEXyRu+EzziescQoXo3tS5RbvU": "Lobbed Bonus Package", # Only 9 children (cf 10 on the above)
		"BwAAADLCudH52S+8IhTTDKHfpQHpUxu2E0jiWscQ4X33uq5N7vY": "Longbow Breath of Terramorphous", # V
		"BwAAADLCuhH52daANxTTDKEfpQGIyhu5E0biWscQ4Xr3ui5Rbvc": "Longbow Pandemic", # V
		"BwAAADJCvDLxmSU8wOjSDKFfgyJbuBi6EQnKascQIW/Uuq5QbvU": "Longbow Meteor Shower", # V
		"BwAAADIBS20A5SK/O1cVT4ECi6gcxQqOBQSK/Bfdx24": "The Afterburner",
		"BwAAADIFS20A5dYAwOjWS7qYugbmPhu7DWqq+cUQYWcwsSlYaeg": "Chitinous Turtle Shield", # V. Massive capacity, slow recharge. Is it best?
		"BwAAADLCshH52dbAN1TfzH4jgiAlwxK8CQ+q6sYQYZkLt49NLv4": "Fire Storm", # V
		"BwAAADLCstH52daAN9TfzH6jgCBJjxK8CQeq6sYQYZkLtI9Nrv8": "Lightning Bolt", # V
		"BwAAADLCshH52daAN9TfzH4jgCCRihK8CQWq6sYQYZkLtY9NLv4": "Fireball", # V
		"BwAAADLCstH5WS68N9TfzH7jgCDRYRK8CQGq6sYQYZlLtI9Nbv8": "Magic Missile", # Best
		# Snipers
		"hwAAADINsYrkKkqfwWh1jdAYI8ki6Ti8n8yJu8cDK+/25C2z5zJN": "Banbury Volcano", # V
		"hwAAADJNsQrjKkifwWiBjYAY08si6di8n8yLu8cDKzv23C1D5DJN": "Fashionable Chère-amie", # V
		# Of dubious but potential value
		"BwAAADIBS20A5S0fPHd5SYkfgMXMtQqOBQSK/JcqOGg": "Heart of the Ancients", # V
		# Unconfirmed or uncategorized
		"BwAAADIiS20A5dYAwOjK7H6jgCEtFRK8Cgm6CsYQoWfwtmlW6fQ": "Blockade",
		"BwAAADLCstH52dbAN1TfzH7jgSCC+RK8CQ2q6sYQYZnLtI9Nrv8": "Chain Lightning", # V
		"BwAAADLCstH52daAN1TfzH7jgSBNXhK8CQ2q6sYQYZnLtI9Nrv8": "Chain Lightning",
		"hwAAADIHS231Aj7PwWgVywGYwdYn/qS8nQMMutMDK4uw1aiB+fdK": "Corrosive Teapot", # V
		"hwAAADIHS231Aj7PwWgVywGYwdYnaGC8nQMMutMDK4uw1aiB+bdJ": "Corrosive Teapot",
		"hwAAADIHS231Aj7PwWgVywGYwdYnmA68nQMMutMDK4uw3aiB+VdJ": "Corrosive Teapot",
		"hwAAADIHS231Aj7PwWgVywGYwdYnE4O8nQMMutMDK4uwNaiB+ZdJ": "Corrosive Teapot",
		"hwAAADIHS231Aj7PwWgVywGYwdYnNHi8nQMMutMDK4uw7aiB+fdK": "Corrosive Teapot",
		"hwAAADIHS231Aj7PwWgVywGYwdYn7au8nQMMutMDK4uw3aiB+ddK": "Corrosive Teapot", # TODO: Cross-product the grip and sight
		"BwAAADI+S20AZS+/OldkWoEUi/wcxQqOBQTKBSjdR5k": "Proficiency Relic", # One of these is purple, one is white
		"BwAAADI+S20AZS//PVcugYEUi9IcxQqOBQTKBSjdR5k": "Proficiency Relic",
		"BwAAADLCutH52dbANxTTjKFfpQHD7Bu5EzriWscQ4Xp3uq5QLv4": "Rubberized Fire Bee",
		"BwAAADIFS20A5dYAwGicy37j2gaYxRuqDW6qOccQYWewtilW6aM": "The Bee",
		"BwAAADIFS20A5dYAwGicy37j2ga32xuqDW6qOccQYWcwsalV6aM": "The Bee",
		"BwAAADIFS20A5dYAwOiey36j2QZEUxuuDVaqWccQ4WQwsKkEKaA": "The Transformer",
		"BwAAADLCstH5WS58ONTfTIsfpgENAhu9E1Ti+sYQYXo3pa5N7vA": "Shock Kiss of Death",
	},
	"Mechromancer": {
		"hwAAADLLrwYA5SKvwWh9L3VcaEA0Hiu9HIyI+dADK8s05K6Sb0RI": "Captain Blade's Orphan Maker",
		"BwAAADI+S20A5dYAwCjOToo8gAOksRm2HQECKscQoWN1tyxRLAs": "Legendary Mechromancer ClassMod",
		"BwAAADIFS20A5dYAwCjOb4E8gCJh9Ri8EQXKSscQ4WcwsSlXaew": "Sponge",
		"BwAAADLCuhHxWS48wOjSzH5jrwGGwRu1E0LiescQYZkLuq5QbvU": "Rolling Thunder",
		"BwAAADI+S20A5dYAwOjJzogdgAPgyRm9HQcC6sYQoWO1tGxQLAs": "Slayer of Terramorphous",
		"BwAAADI+S20ApS3fO3fPg4kegMfM1QqOBQSK/9coeJk": "Bone of the Ancients", # V
		"BwAAADI+S20ApS2fPXf+c4kegMfMtQqORQTK/9coeJk": "Bone of the Ancients",
	},
	"Siren": {
		"hwAAADLKvwT5NjunwWgtbRjdok4hex68XywJu8cDK8sWrOzSZtFJ": "Acuminous Hellfire",
		"BwAAADIFS20A5dYAwOjFy36jlwaOWhu9DQCq+cYQIWYwsKlW6fs": "Flame of the Firehawk",
		"BwAAADI+S20A5dYAwOjJzogdgAME0xudEXKr+cYQoWO1t+xQLAs": "Slayer Of Terramorphous", # Neither of these is strictly better. TODO: Look at their parts.
		"BwAAADI+S20A5dYAwOjJzogdgAN1BhudEXKr+cYQoWM1tyxRLAs": "Slayer Of Terramorphous",
		"BwAAADI+S20A5dYAwOjOjoI8gAOMIhGpHAkK6sYQoWM1t6xQLAs": "Legendary Catalyst",
		"BwAAADI+S20A5dYAwKjODoE8gAN1wBG8HAcK6sYQoWO1tGxQLAs": "Legendary Binder",
		"BwAAADI+S20A5dYAwCjJjpkdgAN6CRubEXyr+cYQoWN1tuxQLAs": "Legendary Siren",
		"BwAAADI+S20A5dYAwKjOzpsdgAPwuBuUEX6r+cYQIWO1tGxQLAs": "Chrono Binder",
	},
	"Assassin": {
		"BwAAADI+S20A5dYAwOjJzogdgAOmFhufEZarmccQoWN1t2xQLAs": "Slayer Of Terramorphous",
		"BwAAADI+S20A5dYAwGjJzogdgANW6BufEZarmccQoWP1t+xQLAs": "Slayer Of Terramorphous",
	},
	"Merc": {
		"BwAAADI+S20A5dYAwKjOzogdgAM/jBueEYCr2ccQoWN1t6xQLAs": "Slayer Of Terramorphous",
		"BwAAADI+S20A5dYAwCjJjqMdgAM3AhugEY6rWccQoW/1t2xRLAs": "Unhinged Hoarder",
		"BwAAADI+S20AJSnfO3fkSYkcgMPMlQqOBQSK/VcqeJk": "Blood of the Ancients", # V
		"BwAAADI+S20AJSmfPXcvwYkcgMPMtQqOBQSK/RfdR5k": "Blood of the Ancients", # Neither is strictly better
	},
	"Soldier": {
		"BwAAADI+S20A5dYAwOjOzqAdgANdoxuVEYKr2ccQoWO1t6xRLAs": "Legendary Berserker Class Mod",
		"BwAAADI+S20A5dYAwOjJzogdgAN14hu8EWyruccQoWO1tOxQLAs": "Slayer Of Terramorphous",
	},
	"Psycho": {
		"BwAAADI+S20A5dYAwCjJDog8gANNZh22HAUK6sYQoWM1t+xQLAs": "Slayer of Terramorphous",
		"BwAAADI+S20A5dYAwOjJDog8gAN2DR22HAUK6sYQoWO1t6xQLAs": "Slayer of Terramorphous",
	},
}

# Requires access to the Gibbed data files.
ASSET_PATH = "../GibbedBL2/Gibbed.Borderlands%s/projects/Gibbed.Borderlands%s.GameInfo/Resources/%s.json"
def get_asset(fn, cache={}):
	if fn not in cache:
		if GAME == "borderlands 2": path = ASSET_PATH % ("2", "2", fn)
		else: path = ASSET_PATH % ("Oz", "Oz", fn)
		with open(path, "rb") as f: cache[fn] = json.load(f)
	return cache[fn]

class ConsumableLE(Consumable):
	"""Little-endian bitwise consumable"""
	def get(self, num):
		return super().get(num)[::-1]
	@classmethod
	def from_bits(cls, data):
		"""Create a bitfield consumable from packed eight-bit data"""
		return cls(''.join(format(x, "08b")[::-1] for x in data))

def bogocrypt(seed, data, direction="decrypt"):
	if not seed: return data
	split = (seed % 32) % len(data)
	if direction == "encrypt": # Encrypting splits first
		data = data[split:] + data[:split]
	if seed > 1<<31: seed |= 31<<32 # Emulate an arithmetic right shift
	xor = seed >> 5
	data = list(data)
	for i, x in enumerate(data):
		# ??? No idea. Got this straight from Gibbed.
		xor = (xor * 0x10A860C1) % 0xFFFFFFFB
		data[i] = x ^ (xor & 255)
	data = bytes(data)
	if direction == "encrypt": return data
	return data[-split:] + data[:-split] # Decrypting splits last

# Many entries in the files are of the form "GD_Weap_SniperRifles.A_Weapons.WeaponType_Vladof_Sniper"
# but the savefile just has "A_Weapons.WeaponType_Vladof_Sniper". The same prefix appears to be used
# for the components of the weapon. So far, I have not figured out how to synthesize the prefix, but
# for any given type, there is only one prefix, so we just calculate from that.
def _category(type_or_bal, _cache = {}):
	if _cache: return _cache.get(type_or_bal, "")
	for lbl in list(get_asset("Item Types")) + list(get_asset("Weapon Types")) \
			+ list(get_asset("Item Balance")) + list(get_asset("Weapon Balance")):
		cat, lbl = lbl.split(".", 1)
		if lbl in _cache and args.verify:
			print("DUPLICATE:")
			print(_cache[lbl] + "." + lbl)
			print(cat + "." + lbl)
		_cache[lbl] = cat
	return _cache[type_or_bal]

@dataclass
class Asset:
	seed: None
	is_weapon: None
	setid: None
	categories: None
	type: "*Types"
	balance: "BalanceDefs"
	brand: "Manufacturers"
	# There are two fields, "Grade" and "Stage". Not sure what the diff
	# is, as they seem to be equal (except when grade is 0 and stage is 1?).
	grade: int
	stage: int
	# Weapons: body grip barrel sight stock elemental acc1 acc2
	# Items: alpha beta gamma delta epsilon zeta eta theta
	pieces: ["*Parts"] * 8
	material: "*Parts"
	pfx: "*Parts"
	title: "*Parts"

	@classmethod
	def decode_asset_library(cls, data):
		orig = data
		seed = int.from_bytes(data[1:5], "big")
		dec = data[:5] + bogocrypt(seed, data[5:], "decrypt")
		if args.verify:
			reconstructed = dec[:5] + bogocrypt(seed, dec[5:], "encrypt")
			if data != reconstructed:
				print("Imperfect reconstruction of weapon/item:")
				print(data)
				print(reconstructed)
				raise AssertionError
		data = dec + b"\xFF" * (40 - len(dec)) # Pad to 40 with 0xFF
		crc16 = int.from_bytes(data[5:7], "big")
		data = data[:5] + b"\xFF\xFF" + data[7:]
		crc = binascii.crc32(data)
		crc = (crc >> 16) ^ (crc & 65535)
		if crc != crc16: raise ValueError("Checksum mismatch")
		config = get_asset("Asset Library Manager")
		if "sets_by_id" not in config:
			# Remap the sets to be keyed by ID - it's more useful that way.
			# TODO: Do this somewhere else, so it's shared with encode_asset_library.
			# Currently, if you call encode without ever having called decode, boom.
			config["sets_by_id"] = {set["id"]: set for set in config["sets"]}
		# The first byte is a version number, with the high
		# bit set if it's a weapon, or clear if it's an item.
		is_weapon = data[0] >= 128
		weap_item = "Weapon" if is_weapon else "Item"
		if (data[0] & 127) != config["version"]: raise ValueError("Version number mismatch")
		uid = int.from_bytes(data[1:5], "little")
		if not uid: return None # For some reason, there are a couple of null items at the end of inventory. They decode fine but aren't items.
		setid = data[7]
		bits = ConsumableLE.from_bits(data[8:])
		def _decode(field):
			cfg = config["configs"][field]
			asset = bits.get(cfg["asset_bits"])
			sublib = bits.get(cfg["sublibrary_bits"] - 1)
			useset = bits.get(1)
			if "0" not in (useset+sublib+asset): return None # All -1 means "nothing here"
			cfg = config["sets_by_id"][setid if useset == "1" else 0]["libraries"][field]
			# print(field, cfg["sublibraries"][int(sublib,2)]["assets"][int(asset,2)])
			return cfg["sublibraries"][int(sublib,2)]["assets"][int(asset,2)]

		ret = {"seed": seed, "is_weapon": is_weapon, "setid": setid}
		for field, typ in cls.__dataclass_fields__.items():
			typ = typ.type
			if typ is None:
				continue # Not being decoded this way
			if typ is int:
				ret[field] = int(bits.get(7), 2)
			elif isinstance(typ, str):
				ret[field] = _decode(typ.replace("*", weap_item))
			elif isinstance(typ, list):
				ret[field] = [_decode(t.replace("*", weap_item)) for t in typ]
			else:
				raise AssertionError("Bad annotation %r" % typ)
		ret["categories"] = (_category(ret["type"]), _category(ret["balance"]), "GD_Weap_Shared_Names")
		ret = cls(**ret)
		if args.verify:
			if ret.encode_asset_library() != orig:
				raise AssertionError("Weapon reconstruction does not match original: %r" % ret)
		return ret

	def encode_asset_library(self):
		# NOTE: Assumes that at least one decode has been done previously.
		bits = []
		config = get_asset("Asset Library Manager")
		# If we were doing this seriously, it would be better to build a
		# mapping from item identifier to (set,subid,asset) triple.
		if self.setid and self.setid in config["sets_by_id"]: sets = (0, self.setid)
		else: sets = (0,)
		categories = _category(self.type), _category(self.balance) # Preferred categories to use
		def _find_asset(field, thing):
			ret = None, None, None
			best = 5
			for useset in sets:
				cfg = config["sets_by_id"][useset]["libraries"][field]
				for sublib, info in enumerate(cfg["sublibraries"]):
					for asset, name in enumerate(info["assets"]):
						if name == thing:
							# TODO: Make sure this is actually safe, then dispose of
							# self.categories altogether. We can fetch it when needed.
							prio = (categories + (info["package"],)).index(info["package"]) # Elephant in Cairo
							if best < 5 and args.verify:
								print("Got duplicate", ret, info["package"], thing)
							if prio < best:
								ret = bool(useset), sublib, asset
								best = prio
			return ret
		fields = []
		def _encode(field, item):
			cfg = config["configs"][field]
			fields.append("%s-%d-%d" % (field, cfg["asset_bits"], cfg["sublibrary_bits"]))
			if item is None:
				bits.append("1" * (cfg["asset_bits"] + cfg["sublibrary_bits"]))
				return
			useset, sublib, asset = _find_asset(field, item)
			if useset is None: raise ValueError("Thing not found: %r => %r" % (field, item))
			bits.append(format(asset, "0%db" % cfg["asset_bits"])[::-1])
			bits.append(format(sublib, "0%db" % (cfg["sublibrary_bits"]-1))[::-1])
			bits.append("1" if useset else "0")
		weap_item = "Weapon" if self.is_weapon else "Item"
		for field, typ in self.__dataclass_fields__.items():
			typ = typ.type
			if typ is None:
				continue # Not being encoded this way
			if typ is int:
				bits.append(format(getattr(self, field), "07b")[::-1])
			elif isinstance(typ, str):
				_encode(typ.replace("*", weap_item), getattr(self, field))
			elif isinstance(typ, list):
				for t, piece in zip(typ, getattr(self, field)):
					_encode(t.replace("*", weap_item), piece)
		bits = "".join(bits)
		bits += "1" * (8 - (len(bits) % 8))
		data = int(bits[::-1], 2).to_bytes(len(bits)//8, "little")
		data = (
			bytes([config["version"] | (128 if self.is_weapon else 0)]) +
			self.seed.to_bytes(4, "big") + b"\xFF\xFF" + bytes([self.setid]) +
			data
		)
		data = data + b"\xFF" * (40 - len(data)) # Pad for CRC calculation
		crc = binascii.crc32(data)
		crc = (crc >> 16) ^ (crc & 65535)
		# data = (data[:5] + crc.to_bytes(2, "big") + data[7:]).rstrip(b"\xFF")
		# print(' '.join(format(x, "08b")[::-1] for x in data))
		# print(' '.join(format(x, "08b")[::-1] for x in (dec[:5] + b"\xFF\xFF" + dec[7:])))
		return data[:5] + bogocrypt(self.seed, (crc.to_bytes(2, "big") + data[7:]).rstrip(b"\xFF"), "encrypt")

	def get_title(self):
		typeinfo = get_asset("Weapon Types" if self.is_weapon else "Item Types")[_category(self.type) + "." + self.type]
		if typeinfo.get("has_full_name"):
			# The item's type fully defines its title. This happens with a number
			# of unique and/or special items.
			return typeinfo["name"]
		# Otherwise, build a name from a prefix (possibly) and a title.
		# The name parts have categories and I don't yet know how to reliably list them.
		names = get_asset("Weapon Name Parts" if self.is_weapon else "Item Name Parts")
		cats = _category(self.type), _category(self.balance), "GD_Weap_Shared_Names"
		pfxinfo = None
		if self.pfx:
			for cat in cats:
				pfxinfo = names.get(cat + "." + self.pfx)
				if pfxinfo: break
			# pfxinfo has a name (unless it's a null prefix), and a uniqueness flag. No idea what that one is for.
		if self.title:
			for cat in cats:
				titinfo = names.get(cat + "." + self.title)
				if titinfo: break
			title = titinfo["name"] if titinfo else self.title
		else: title = "<no title>"
		if pfxinfo and "name" in pfxinfo: title = pfxinfo["name"] + " " + title
		return title

	def __repr__(self):
		if self.grade == self.stage: lvl = "Lvl %d" % self.grade
		else: lvl = "Level %d/%d" % (self.grade, self.stage)
		type = self.type.split(".", 1)[1].replace("WT_", "").replace("WeaponType_", "").replace("_", " ")
		ret = "%s %s (%s)" % (lvl, self.get_title(), type) + ("\n" + " + ".join(filter(None, self.pieces))) * args.pieces
		if args.itemids: ret += " {%s}" % armor_serial(self.encode_asset_library())
		if args.raw: ret += "\n" + ", ".join("%s=%r" % (f, getattr(self, f)) for f in self.__dataclass_fields__)
		return ret
	#if args.raw: del __repr__ # For a truly-raw view (debugging mode).

def decode_tree(bits):
	"""Decode a (sub)tree from the given sequence of bits

	Returns either a length-one bytes, or a tuple of two trees (left
	and right). Consumes either a 1 bit and then eight data bits, or
	a 0 bit and then two subtrees.
	"""
	if bits.get(1) == "1": # Is it a leaf?
		return int(bits.get(8), 2)
	# Otherwise, it has subnodes.
	return (decode_tree(bits), decode_tree(bits))
def huffman_decode(data, size):
	bits = Consumable.from_bits(data)
	root = decode_tree(bits)
	global last_huffman_tree; last_huffman_tree = root
	ret = []
	while len(ret) < size:
		cur = root
		while isinstance(cur, tuple):
			cur = cur[bits.get(1) == "1"]
		ret.append(cur)
	# The residue doesn't always consist solely of zero bits. I'm not sure
	# why, and I have no idea how to replicate it. Hopefully it doesn't
	# matter.
	residue = bits.peek()
	global last_huffman_residue; last_huffman_residue = residue
	if len(residue) >= 8: raise ValueError("Too much compressed data - residue " + residue)
	return bytes(ret)

def huffman_encode(data):
	if not data: return data # Probably wrong but should never happen anyway
	# First, build a Huffman tree by figuring out which bytes are most common.
	counts = collections.Counter(data)
	while len(counts) > 1:
		# Pick the two least common and join them
		(left, lfreq), (right, rfreq) = counts.most_common()[-2:]
		del counts[left], counts[right]
		counts[(left, right)] = lfreq + rfreq
	[head] = counts # Grab the sole remaining key
	if args.verify: head = last_huffman_tree # Hack: Reuse the tree from the last decode (gives bit-for-bit identical compression)
	# We now should have a Huffman tree where every node is either a leaf
	# (a single byte value) or a tuple of two nodes with approximately
	# equal frequency. Next, we turn that tree into a bit sequence that
	# decode_tree() can parse, and also (for convenience) flatten it into
	# a lookup table mapping byte values to their bit sequences.
	bits = {}
	ret = []
	def _flatten(node, seq):
		if isinstance(node, tuple):
			ret.append("0")
			_flatten(node[0], seq + "0")
			_flatten(node[1], seq + "1")
		else:
			ret.append("1" + format(node, "08b"))
			bits[node] = seq
	_flatten(head, "")
	# Finally, the easy bit: turn every data byte into a bit sequence.
	ret.extend(bits[char] for char in data)
	ret = "".join(ret)
	spare = len(ret) % 8
	if spare:
		# Hack: Reuse the residue from the last decode. I *think* this is just
		# junk bits that are ignored on load.
		if args.verify and len(last_huffman_residue) == 8-spare: ret += last_huffman_residue
		else: ret += "0" * (8-spare)
	return int(ret, 2).to_bytes(len(ret)//8, "big")

def get_varint(data):
	"""Parse a protobuf varint out of the given data

	It's like a little-endian version of MIDI's variable-length
	integer. I don't know why Google couldn't just adopt what
	already existed.
	"""
	scale = ret = 0
	byte = 128
	while byte > 127:
		byte = data.get(1)[0]
		ret |= (byte&127) << scale
		scale += 7
	return ret

def build_varint(val):
	"""Build a protobuf varint for the given value"""
	data = []
	while val > 127:
		data.append((val & 127) | 128)
		val >>= 7
	data.append(val)
	return bytes(data)

# Handle protobuf wire types by destructively reading from data
protobuf_decoder = [get_varint] # Type 0 is varint
@protobuf_decoder.append
def protobuf_64bit(data):
	return data.get(8)
@protobuf_decoder.append
def protobuf_length_delimited(data):
	return data.get(get_varint(data))
@protobuf_decoder.append
def protobuf_start_group(data):
	raise Exception("Unimplemented")
@protobuf_decoder.append
def protobuf_end_group(data):
	raise Exception("Unimplemented")
@protobuf_decoder.append
def protobuf_32bit(data):
	return data.get(4)

int32, int64 = object(), object() # Pseudo-types. On decode they become normal integers.

class ProtoBuf:
	# These can be packed into arrays.
	PACKABLE = {int: get_varint, int32: protobuf_decoder[1], int64: protobuf_decoder[5]}

	@staticmethod
	def decode_value(val, typ, where):
		if isinstance(val, int): return val # Only for varints, which should always be ints
		assert isinstance(val, bytes)
		if isinstance(typ, type) and issubclass(typ, ProtoBuf): return typ.decode_protobuf(val)
		if typ in (int32, int64): return int.from_bytes(val, "little")
		if typ is float: return struct.unpack("<f", val) # TODO: Should this be subscripted [0]?
		if typ is str: return val.decode("UTF-8")
		if typ is bytes: return val
		if typ in (list, dict): return val # TODO
		raise ValueError("Unrecognized annotation %r in %s: data %r" % (typ, where, val[:64]))
	@classmethod
	def decode_protobuf(cls, data):
		fields = list(cls.__dataclass_fields__)
		data = Consumable(data)
		values = {}
		while data:
			idx, wiretype = divmod(get_varint(data), 8)
			field = fields[idx - 1]
			val = protobuf_decoder[wiretype](data)
			typ = cls.__dataclass_fields__[field].type
			if isinstance(typ, list):
				lst = values.setdefault(field, [])
				if typ[0] in cls.PACKABLE and wiretype == 2:
					# Packed integers.
					val = Consumable(val)
					while val:
						lst.append(cls.PACKABLE[typ[0]](val))
				else:
					lst.append(cls.decode_value(val, typ[0], cls.__name__ + "." + field))
			else:
				values[field] = cls.decode_value(val, typ, cls.__name__ + "." + field)
		return cls(**values)

	@staticmethod
	def encode_value(val, typ, where):
		if isinstance(val, int):
			if typ is int32: return val.to_bytes(4, "little")
			if typ is int64: return val.to_bytes(8, "little")
			return build_varint(val)
		if isinstance(val, bytes): return val # Stuff we can't decode gets returned untouched
		if hasattr(val, "encode_protobuf"): return val.encode_protobuf()
		if typ is str: return val.encode("UTF-8")
		if typ is float: return struct.pack("<f", val)
		if isinstance(typ, list) and typ[0] is int:
			# Packed integers (supporting varint only)
			return b"".join(build_varint(n) for n in val)
		raise ValueError("Unrecognized annotation %r in %s: data %r" % (typ, where, val))
	def encode_protobuf(self):
		data = []
		for idx, field in enumerate(self.__dataclass_fields__):
			val = getattr(self, field)
			if not val and val != 0: continue # Skip empties, except that a 0 int should still get encoded
			typ = self.__dataclass_fields__[field].type
			if typ is int:
				# Wiretype 0 integer
				data.append(build_varint(idx * 8 + 8))
				data.append(build_varint(val))
				continue
			if isinstance(typ, list) and typ[0] is not int:
				typ = typ[0]
				for val in val:
					val = self.encode_value(val, typ, self.__class__.__name__ + "." + field + "[*]")
					assert isinstance(val, bytes)
					data.append(build_varint(idx * 8 + 10))
					data.append(build_varint(len(val)))
					data.append(val)
				continue
			val = self.encode_value(val, typ, self.__class__.__name__ + "." + field)
			assert isinstance(val, bytes)
			data.append(build_varint(idx * 8 + 10))
			data.append(build_varint(len(val)))
			data.append(val)
		return b"".join(data)

# Stub types that are used by SaveFile
SkillData = ResourceData = ItemData = Weapon = MissionPlaythrough = bytes
DLCData = RegionGameStage = WorldDiscovery = WeaponMemento = ItemMemento = bytes
Challenge = OneOffChallenge = Lockout = VehicleSkin = bytes

@dataclass
class Color(ProtoBuf):
	alpha: int
	red: int
	green: int
	blue: int
	def __repr__(self): return "RGBA<%d,%d,%d,%d>" % (self.red, self.green, self.blue, self.alpha)
@dataclass
class UIPreferences(ProtoBuf):
	name: str
	color1: Color
	color2: Color
	color3: Color

@dataclass
class InventorySlots(ProtoBuf):
	backpack: int
	weapons: int
	num_quick_slots_flourished: int # No idea what this is.

@dataclass
class BankSlot(ProtoBuf):
	serial: bytes
	# Yes, that's all there is. Just a serial number. Packaged up in a protobuf.
	def prefix(self): return "Bank: "
	def order(self): return 8

@dataclass
class PackedItemData(ProtoBuf):
	serial: bytes
	quantity: int
	equipped: int
	mark: int
	def prefix(self): return "Equipped: " if self.equipped else ""
	def order(self): return 5 if self.equipped else 6

@dataclass
class PackedWeaponData(ProtoBuf):
	serial: bytes
	quickslot: int
	mark: int
	unknown4: int = None
	def prefix(self): return "Weapon %d: " % self.quickslot if self.quickslot else ""
	def order(self): return self.quickslot or 6

@dataclass
class SaveFile(ProtoBuf):
	playerclass: str
	level: int
	exp: int
	general_skill_points: int
	specialist_skill_points: int # No idea what the diff is btwn these
	money: [int] # [money, Eridium/Moonstones, Seraph tokens, unknown, Torgue tokens, then eight more unknowns]
	playthroughs_completed: int
	skills: [SkillData]
	unknown9: [int] = None
	unknown10: [int] = None
	resources: [ResourceData] = None
	items: [ItemData] = None
	inventory_slots: InventorySlots = None
	weapons: [Weapon] = None
	stats: bytes = b"" # ?? Opaque (for now)
	fasttravel: [str] = None
	last_fasttravel: str = ""
	missions: [MissionPlaythrough] = None
	preferences: UIPreferences = None
	savegameid: int = 0
	plotmission: int = 0
	unknown22: int = None
	codesused: [int] = None
	codes_needing_notifs: [int] = None
	total_play_time: int = 0
	last_save_date: str = ""
	dlc: [DLCData] = None
	unknown28: [str] = None
	region_game_stages: [RegionGameStage] = None
	world_discovery: [WorldDiscovery] = None
	badass_mode: int = 0
	weapon_mementos: [WeaponMemento] = None
	item_mementos: [ItemMemento] = None
	save_guid: bytes = b""
	applied_customizations: [str] = None # Current skins?
	black_market: [int] = None
	active_mission: int = 0
	challenges: [Challenge] = None
	level_challenge_unlocks: [int] = None
	one_off_level_challenges: [OneOffChallenge] = None
	bank: [BankSlot] = None
	challenge_prestiges: int = 0
	lockout_list: [Lockout] = None
	is_dlc_class: int = None
	dlc_class_package: int = None
	fully_explored: [str] = None
	unknown47: [bytes] = None
	golden_keys: int = 0 # Number "notified", whatever that means.
	last_playthrough: int = 0
	show_new_playthrough_notif: int = 0
	rcvd_default_weap: int = 0
	queued_training_msgs: [str] = None
	packed_item_data: [PackedItemData] = None
	packed_weapon_data: [PackedWeaponData] = None
	awesome_skill_disabled: int = 0
	max_bank_slots: int = 0 # Might be useful when looking for a place to put stuff
	vehicle_skins: [VehicleSkin] = None
	if GAME == "borderlands the pre-sequel":
		body_switches: bytes = b""
		player_flags: [int] = None
		vehicle_steering_mode: int = 0
		discovered_compass_icons: [bytes] = None
		suppress_oxygen_notifs: int = 0
	else:
		vehicle_steering_mode: int = 0
	has_played_uvhm: int = None
	overpower_levels: int = None
	last_overpower_choice: int = None

class SaveFileFormatError(Exception): pass

def parse_savefile(fn):
	with open(fn, "rb") as f: data = Consumable(f.read())
	# PC builds, presumably including Linux builds, should be
	# little-endian and LZO-compressed. Some retrievals are
	# forced big-endian, others vary by platform. Dunno why.
	endian = "little"
	hash = data.get(20)
	if hash != hashlib.sha1(data.peek()).digest():
		raise SaveFileFormatError("Hash fails to validate")
	uncompressed_size = int.from_bytes(data.get(4), "big")
	if uncompressed_size > 0x40000:
		raise SaveFileFormatError("TODO: handle chunked decompression")
	raw = lzo.decompress(data.peek(), False, uncompressed_size)
	if len(raw) != uncompressed_size:
		raise SaveFileFormatError("Got wrong amount of data back (%d != %d)" % (len(raw), uncompressed_size))
	if args.verify:
		# LZO compression isn't stable or consistent enough to compare the
		# compressed bytes to what we got from the file. But let's just
		# quickly make sure we can get something back, at least.
		comp = lzo.compress(raw, 1, False)
		if lzo.decompress(comp, False, uncompressed_size) != raw:
			print("Recompression gives something that we didn't get first time!")
			return ""
	# Okay. Decompression complete. Now to parse the actual data.
	data = Consumable(raw)
	size = int.from_bytes(data.get(4), "big")
	if size != len(data):
		raise SaveFileFormatError("Size doesn't match remaining bytes - corrupt file? chunked?");
	if data.get(3) != b"WSG":
		raise SaveFileFormatError("Invalid magic number - corrupt file?")
	if int.from_bytes(data.get(4), endian) != 2:
		raise SaveFileFormatError("Unsupported version number (probable corrupt file)")
	crc = int.from_bytes(data.get(4), endian)
	uncomp_size = int.from_bytes(data.get(4), endian) # Gibbed uses a *signed* 32-bit int here
	# For some bizarre reason, the data in here is Huffman-compressed.
	# The whole file has already been LZO-compressed. No point compressing twice!
	# Not sure what the last four bytes are. The end of the compressed sequence
	# finishes off the current byte, and then there are always four more bytes.
	if data.peek()[-4:] != b"\xd4\x93\x9f\x1a":
		raise SaveFileFormatError("Different last four bytes: %r" % data.peek()[-4:])
	data = huffman_decode(data.peek()[:-4], uncomp_size)
	if crc != binascii.crc32(data):
		raise SaveFileFormatError("CRC doesn't match (%d vs %d)" % (crc, binascii.crc32(data)))
	if args.verify:
		reconstructed = huffman_encode(data)
		reconstructed = b"".join([
			(3 + 4 + 4 + 4 + len(reconstructed) + 4).to_bytes(4, "big"),
			b"WSG",
			(2).to_bytes(4, endian),
			binascii.crc32(data).to_bytes(4, endian),
			len(data).to_bytes(4, endian),
			reconstructed,
			b"\xd4\x93\x9f\x1a",
		])
		if reconstructed != raw:
			if len(reconstructed) != len(raw):
				print("Imperfect recompression:", len(raw), len(reconstructed))
				return ""
			print("Mismatched after recompression", len(raw))
			for ofs in range(0, len(raw), 64):
				old = raw[ofs:ofs+64]
				new = reconstructed[ofs:ofs+64]
				if old != new:
					print(ofs, old)
					print(ofs, new)
			return ""
	savefile = SaveFile.decode_protobuf(data)
	if args.verify:
		reconstructed = savefile.encode_protobuf()
		if reconstructed != data:
			print("Imperfect reconstruction:", len(data))
			for sz in range(64, max(len(data), len(reconstructed))+65, 64):
				if data[:sz] == reconstructed[:sz]: continue
				print(sz-64)
				print(data[sz-64:sz])
				print(reconstructed[sz-64:sz])
				break
			return ""
	cls = get_asset("Player Classes")[savefile.playerclass]["class"]
	# The packed_weapon_data and packed_item_data arrays contain the correct
	# number of elements for the inventory items. (Equipped or backpack is
	# irrelevant, but anything that isn't a weapon ('nade mod, class mod, etc)
	# goes in the item data array.)
	items = []
	for item in (savefile.packed_weapon_data or []) + (savefile.packed_item_data or []) + (savefile.bank or []):
		if args.loot_filter is None: break
		it = Asset.decode_asset_library(item.serial)
		if not it: continue
		for filter, filterargs in args.loot_filter:
			if not filter(it, *filterargs): break
		else:
			items.append((item.order(), -it.grade, item.prefix() + repr(it)))
	ret = "Level %d (%dxp) %s: \x1b[1;31m%s\x1b[0m (%d+%d items)" % (savefile.level, savefile.exp, cls,
		savefile.preferences.name, len(savefile.packed_weapon_data), len(savefile.packed_item_data) - 2)
	items.sort()
	ret += "".join("\n" + desc for order, lvl, desc in items if order >= 0)
	if args.synth is not None:
		# Make changes to the save file before synthesizing
		savefile.preferences.name = "PATCHED" # Easy way to see what's happening
		for synth, synthargs in args.synth: synth(savefile, *synthargs)

		data = savefile.encode_protobuf()
		reconstructed = huffman_encode(data)
		reconstructed = b"".join([
			(3 + 4 + 4 + 4 + len(reconstructed) + 4).to_bytes(4, "big"),
			b"WSG",
			(2).to_bytes(4, endian),
			binascii.crc32(data).to_bytes(4, endian),
			len(data).to_bytes(4, endian),
			reconstructed,
			b"\xd4\x93\x9f\x1a",
		])
		comp = len(reconstructed).to_bytes(4, "big") + lzo.compress(reconstructed, 1, False)
		comp = hashlib.sha1(comp).digest() + comp
		with open("synthesized.sav", "wb") as f: f.write(comp)
	return ret

if args.platform == "native":
	dir = os.path.expanduser("~/.local/share/aspyr-media/" + GAME + "/willowgame/savedata")
else:
	appid = "261640" if GAME == "borderlands the pre-sequel" else "49520"
	dir = os.path.expanduser("~/.steam/steam/steamapps/compatdata/" + appid +
		"/pfx/drive_c/users/steamuser/My Documents/My Games/Borderlands 2/WillowGame/SaveData")
if args.player == "list":
	print("Player IDs available:")
	for player in sorted(os.listdir(dir)):
		print("--player", player)
	sys.exit(0)
if args.file:
	try: os.stat(args.file)
	except FileNotFoundError: pass
	else:
		try: print(parse_savefile(args.file))
		except SaveFileFormatError as e: print(e.args[0])
		sys.exit(0)
dir = os.path.join(dir, args.player or os.listdir(dir)[0]) # If this bombs, you might not have any saves
file = (args.file or "").replace(".sav", "")
for fn in sorted(os.listdir(dir)):
	if not fn.endswith(".sav"): continue
	if not fnmatch(fn, "*" + file + ".sav"): continue
	print(fn, end="... ")
	try: print(parse_savefile(os.path.join(dir, fn)))
	except SaveFileFormatError as e: print(e.args[0])
if file == "synth":
	try: print(parse_savefile("synthesized.sav"))
	except SaveFileFormatError as e: print(e.args[0])
if args.library:
	for id in args.library.split(","):
		if '{' in id: id = id.split("{")[1].split("}")[0]
		if not id: continue
		serial = base64.b64decode(id.encode("ascii") + b"====")
		obj = Asset.decode_asset_library(serial)
		obj.grade = obj.stage = obj.seed = 50
		serial = obj.encode_asset_library()
		id = base64.b64encode(serial).decode("ascii").strip("=")
		for clsitems in library.values():
			if id in clsitems: break
		else: print('\t\t"%s": "%s",' % (id, obj.get_title()))
