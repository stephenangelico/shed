import choc, {set_content, DOM, on} from "https://rosuav.github.io/shed/chocfactory.js";
const {TABLE, TR, TD, INPUT, SELECT, OPTION} = choc;

//TODO: Crib these from the files somehow so they don't have to be updated.
const machines = {
	constructor: {
		inputs: 1,
		outputs: 1,
		cost: 4, //MW, or MJ/second
	},
	assembler: {
		inputs: 2,
		outputs: 1,
		cost: 15,
	},
};
const resources = {
	FlowerPetals: {sink: 10, energy: 100, name: "Flower Petals"},
	Leaves: {sink: 3, energy: 15, name: "Leaves"},
	GenericBioMass: {sink: 12, energy: 180, name: "Biomass"},
};
const resource_ids = Object.keys(resources); //We iterate over resources a lot.

let machine = null;

function update_totals() {
	["input", "output"].forEach(kwd => {
		let sink = 0, energy = 0;
		for (let i = 0; i < machine[kwd + "s"]; ++i) {
			const res = resources[DOM("#" + kwd + i).value];
			if (!res) {console.warn("Borked " + kwd, DOM("#" + kwd + i).value); continue;}
			const qty = DOM("#" + kwd + "qty" + i).value|0;
			sink += res.sink * qty;
			energy += res.energy * qty;
		}
		if (energy) set_content("#" + kwd + "_total", `${sink} sink value, ${energy} MJ`);
		else set_content("#" + kwd + "_total", `${sink} sink value`);
	});
}
on("input", "#recipe input,select", update_totals);

function RESOURCE(attrs) {
	//TODO: optgroup these as appropriate
	return SELECT(attrs, resource_ids.map(r => OPTION({value: r}, resources[r].name)));
}

function select_machine(id) {
	machine = machines[id];
	const rows = [];
	for (let i = 0; i < machine.inputs; ++i)
		rows.push(TR([TD("Input"), TD([RESOURCE({id: "input" + i}), INPUT({id: "inputqty" + i, type: "number", value: 1})])]));
	rows.push(TR([TD("Total"), TD({id: "input_total"})]));
	rows.push(TR(TD({colSpan: 2})));
	for (let i = 0; i < machine.outputs; ++i)
		rows.push(TR([TD("Output"), TD([RESOURCE({id: "output" + i}), INPUT({id: "outputqty" + i, type: "number", value: 1})])]));
	rows.push(TR([TD("Total"), TD({id: "output_total"})]));
	const stuff = [TABLE({border: 1}, rows)];
	set_content("#recipe", stuff);
	update_totals();
}
on("click", 'input[name="machine"]', e => select_machine(e.match.value));
select_machine("constructor");
