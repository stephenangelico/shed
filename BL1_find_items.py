import os.path
import struct
from dataclasses import dataclass # ImportError? Upgrade to Python 3.7 or pip install dataclasses

class Consumable:
	"""Like a bytes/str object but can be consumed a few bytes/chars at a time"""
	def __init__(self, data):
		self.data = data
		self.eaten = 0
		self.left = len(data)
	def get(self, num):
		"""Destructively read the next num bytes/chars of data"""
		if num > self.left: raise ValueError("Out of data!")
		ret = self.data[self.eaten : self.eaten + num]
		self.eaten += num
		self.left -= num
		return ret
	def int(self, size=4, order="little"): return int.from_bytes(self.get(size), order)
	def hollerith(self, size=4, order="little"): return self.get(self.int(size, order))
	def str(self): return self.hollerith().rstrip(b"\x00").decode("ascii")
	def __len__(self): return self.left
	def peek(self): return self.data[self.eaten:] # Doubles as "convert to bytes/str"
	@classmethod
	def from_bits(cls, data):
		"""Create a bitfield consumable from packed eight-bit data"""
		return cls(''.join(format(x, "08b") for x in data))

class SaveFileFormatError(Exception): pass

def decode_dataclass(data, typ):
	if hasattr(typ, "__dataclass_fields__"):
		values = {}
		for field in typ.__dataclass_fields__.values():
			values[field.name] = decode_dataclass(data, field.type)
		return typ(**values)
	if isinstance(typ, list):
		if len(typ) == 2:
			# Hack because I have no idea what's going on here
			# Decode up to a sentinel
			ret = [decode_dataclass(data, typ[0])]
			while ret[-1] != typ[1]: ret.append(decode_dataclass(data, typ[0]))
			return ret
		return [decode_dataclass(data, typ[0]) for _ in range(data.int())]
	if isinstance(typ, tuple):
		return tuple(decode_dataclass(data, t) for t in typ)
	if isinstance(typ, int):
		return data.get(typ)
	if isinstance(typ, bytes):
		ret = data.get(len(typ))
		assert ret == typ
		return ret
	if typ is int:
		return data.int()
	if isinstance(typ, range):
		# Bounded integer
		l = len(typ)
		ret = data.int(1 if l <= 256 else 2 if l <= 65536 else 4)
		# TODO: Support signed numbers eg range(-128, 127)
		assert ret in typ
		return ret
	if typ is bytes:
		return data.hollerith()
	if typ is str:
		return data.str()
	if typ is float:
		return struct.unpack("f", data.get(4))[0]
	if typ is print:
		print(data.peek()[:16], len(data))
		return None
	raise TypeError("need to implement: %r %r" % (type(type), typ))

@dataclass
class Skill:
	name: str
	level: int
	progress: int # Possibly progress to next level?? Applies only to proficiencies.
	state: int # Always either -1 or 1

@dataclass
class Ammo:
	cat: str
	pool: str
	amount: float # WHY??? Ammo regen maybe???
	capacity: int # 0 = base capacity, 1 = first upgrade, etc

@dataclass
class Item: # Can't find item level
	grade: str
	type: str
	pieces: (str,) * 4
	mfg: str
	prefix: str
	title: str
	values: (int,) * 5 # values[2] seems to be equipped state (1 or 0)

@dataclass
class Weapon:
	grade: str
	mfg: str
	type: str
	pieces: (str,) * 8
	material: str
	prefix: str
	title: str
	ammo: int
	quality: range(65536)
	level: range(65536)
	slot: int # 1-4 or 0 for backpack
	junk: int
	locked: int

@dataclass
class BankItem: # Bank items have things in a different order. Weird.
	type: str
	grade: str
	mfg: str
	pieces: (str,) * 4
	prefix: str
	title: str

@dataclass
class Mission:
	mission: str
	unknowns: (int, int, int) # Always 4, 0, 0 for done missions, I think? Maybe a status or something.
	goals: [(str, int)] # Always 0 of these for done missions

@dataclass
class Savefile:
	sig: b"WSG"
	ver: b"\2\0\0\0"
	type: 4
	revision: int
	cls: str
	level: int
	xp: int
	zeroes1: bytes(8)
	money: int
	unknown3: 4
	skills: [Skill]
	zeroes2: bytes(8)
	unknown4: int
	zeroes3: bytes(4)
	ammo: [Ammo]
	items: [Item]
	backpacksize: int
	weaponslots: int
	weapons: [Weapon]
	unknown6: bytes # always 1347 bytes long, unknown meaning - something to do with challenges?
	fasttravels: [str] # Doesn't include DLCs that have yet to be tagged up
	last_location: str # You'll spawn at this location
	zeroes4: bytes(12)
	unknown7: int
	zeroes5: bytes(4)
	unknown8: (int,) * 5 # [1-4, 39, ??, 3, 0] where the middle one is higher on more-experienced players
	current_mission: str # I think? Maybe?
	missions: [Mission]
	unknown9: ((int, str), (int, str), (int,)*4, (int, str), (int, str), (int,) * 5) # ?? Seem to be more missions?
	timestamp: str # Last saved? I think?
	name: str
	colours: (int, int, int)
	enhancedblock: 0x55 # ???
	unknown10: int
	promocodes: [int]
	promocodes_new: [int]
	unknown10a: 8
	echo_recordings: [(str, int, int)] # No idea what the ints mean, probably flags about having heard them or something
	shim: print
	unknown11: [int, 0x43211234] # Unknown values - more of them if you've finished the game??
	unknown12: 9
	bank_weapons: [(14, str, str, str, 13, str, str, str, 13, str, str, str, 3, print)]
	unknown13: 42
	unknown: int
	unknown_weapons: [Weapon] # Some sort of special weapons
	unknown99: (int,) * 6
	zeroes6: bytes(80)

def parse_savefile(fn):
	with open(fn, "rb") as f: data = Consumable(f.read())
	savefile = decode_dataclass(data, Savefile)
	assert savefile.last_location in savefile.fasttravels
	print("%s (level %d %s, $%d)" % (savefile.name, savefile.level, savefile.cls.split("_")[-1], savefile.money))
	for weapon in sorted(savefile.weapons, key=lambda w: w.slot or 5):
		print("%d: [%d-%d] %s %s" % (weapon.slot, weapon.level, weapon.quality, weapon.prefix.split(".")[-1], weapon.title.split(".")[-1]))
	# print(", ".join(hex(x) for x in savefile.unknown13))
	# print(*savefile.bank_weapons, sep="\n")
	assert len(data) == 0
	return ""

dir = os.path.expanduser("~/.steam/steam/steamapps/compatdata/729040/pfx/drive_c/users/steamuser/My Documents/My Games/Borderlands Game of the Year/Binaries/SaveData")
for fn in sorted(os.listdir(dir)):
	if not fn.endswith(".sav"): continue
	print(fn, end="... ")
	try: print(parse_savefile(os.path.join(dir, fn)))
	except SaveFileFormatError as e: print(e.args[0])
	print()

''' Gear
1: 32 Volcano - Maliwan sniper
2: 20 Hellfire - Maliwan SMG
3: 37 Eridian Lightning
4: 36 Torgue launcher
-: 34 Maliwan SMG
-: 33 Hyperion Repeater
-: 28 Eridian Cannon
e: 34 Pangolin shield
e: 31 Anshin transfusion grenade
e: 16 Dahl class mod, Mercenary
-: 31 Tediore shield

Money 1102561 0x10d2e1 or float \x08\x97\x86\x49
'''

# 000020c5 43 05
# 0000260c 32 00 00 00
