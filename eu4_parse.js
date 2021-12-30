//Not to be confused with eu4_parse.json which is a cache
import choc, {set_content, DOM} from "https://rosuav.github.io/shed/chocfactory.js";
const {A, ABBR, DETAILS, DIV, FORM, H1, INPUT, LABEL, LI, P, SPAN, SUMMARY, TABLE, TD, TH, TR, UL} = choc; //autoimport

function table_head(headings) {
	if (typeof headings === "string") headings = headings.split(" ");
	return TR(headings.map(h => TH(h))); //TODO: Click to sort
}

let countrytag = "";
function PROV(id, name) {
	return DIV({className: "province"}, [name, SPAN({className: "goto-province", title: "Go to #" + id, "data-provid": id}, "⤳")]);
}

on("click", ".goto-province", e => {
	ws_sync.send({cmd: "goto", tag: countrytag, province: e.match.dataset.provid});
});

on("click", ".pickbuilding", e => {
	ws_sync.send({cmd: "highlight", building: e.match.dataset.bldg});
});

export function render(state) {
	//Set up one-time structure. Every subsequent render will update within that.
	if (!DOM("#error")) set_content("main", [
		DIV({id: "error", className: "hidden"}), DIV({id: "now_parsing", className: "hidden"}),
		DIV({id: "menu", className: "hidden"}),
		H1({id: "player"}),
		DETAILS({id: "cot"}, SUMMARY("Centers of Trade")),
		DETAILS({id: "monuments"}, SUMMARY("Monuments")),
		DETAILS({id: "favors"}, SUMMARY("Favors")),
		DETAILS({id: "wars"}, SUMMARY("Wars")),
		DETAILS({id: "expansions"}, SUMMARY("Building expansions")),
		DIV({id: "options"}, [ //Positioned fixed in the top corner
			DETAILS({id: "highlight"}, SUMMARY("Building highlight")),
		]),
		//TODO: Have DETAILS/SUMMARY nodes for every expandable, such that,
		//whenever content is updated, they remain in their open/closed state
	]);

	if (state.error) {
		set_content("#error", state.error).classList.remove("hidden");
		return;
	}
	set_content("#error", "").classList.add("hidden");
	if (state.parsing) set_content("#now_parsing", "Parsing savefile...").classList.remove("hidden");
	else set_content("#now_parsing", "").classList.add("hidden");
	if (state.menu) {
		function lnk(dest) {return A({href: "/tag/" + encodeURIComponent(dest)}, dest);}
		set_content("#menu", [
			"Save file parsed. Pick a player nation to monitor, or search for a country:",
			UL(state.menu.map(c => LI([lnk(c[0]), " - ", lnk(c[1])]))),
			FORM([
				LABEL(["Enter tag or name:", INPUT({name: "q", placeholder: "SPA"})]),
				INPUT({type: "submit", value: "Search"}),
			]),
		]).classList.remove("hidden");
		return;
	}
	if (state.name) set_content("#player", state.name);
	if (state.tag) countrytag = state.tag;
	if (state.cot) {
		const content = [SUMMARY(`Max level CoTs [${state.cot.level3}/${state.cot.max}]`)];
		for (let kwd of ["upgradeable", "developable"]) {
			const cots = state.cot[kwd];
			if (!cots.length) continue;
			content.push(TABLE({id: kwd, border: "1"}, [
				TR(TH({colSpan: 4}, `${kwd[0].toUpperCase()}${kwd.slice(1)} CoTs:`)),
				cots.map(cot => TR({className: cot.noupgrade === "" ? "highlight" : ""}, [
					TD(PROV(cot.id, cot.name)), TD("Lvl "+cot.level), TD("Dev "+cot.dev), TD(cot.noupgrade)
				])),
			]));
		}
		set_content("#cot", content);
	}
	if (state.monuments) set_content("#monuments", [
		SUMMARY(`Monuments [${state.monuments.length}]`),
		TABLE({border: "1"}, [
			TR([TH("Province"), TH("Tier"), TH("Project"), TH("Upgrading")]),
			state.monuments.map(m => TR([TD(PROV(m[1], m[3])), TD(m[2]), TD(m[4]), TD(m[5])])),
		]),
	]);
	if (state.favors) {
		let free = 0, owed = 0, owed_total = 0;
		function compare(val, base) {
			if (val <= base) return val.toFixed(3);
			return ABBR({title: val.toFixed(3) + " before cap"}, base.toFixed(3));
		}
		const cooldowns = state.favors.cooldowns.map(cd => {
			if (cd[1] === "---") ++free;
			return TR({className: cd[1] === "---" ? "highlight" : ""}, cd.slice(1).map(TD));
		});
		const countries = Object.entries(state.favors.owed).sort((a,b) => b[1][0] - a[1][0]).map(([c, f]) => {
			++owed_total; if (f[0] >= 10) ++owed;
			return TR({className: f[0] >= 10 ? "highlight" : ""}, [TD(c), f.map((n,i) => TD(compare(n, i ? +state.favors.cooldowns[i-1][4] : n)))]);
		});
		set_content("#favors", [
			SUMMARY(`Favors [${free}/3 available, ${owed}/${owed_total} owe ten]`),
			TABLE({border: "1"}, cooldowns),
			TABLE({border: "1"}, [
				table_head("Country Favors Ducats Manpower Sailors"),
				countries
			]),
		]);
	}
	if (state.wars) {
		//For each war, create or update its own individual DETAILS/SUMMARY. This allows
		//individual wars to be collapsed as uninteresting without disrupting others.
		set_content("#wars", [SUMMARY("Wars: " + state.wars.length), state.wars.map(war => {
			let id = "warinfo-" + war.name.toLowerCase().replace(/[^a-z]/g, " ").replace(/ +/g, "-");
			//It's possible that a war involving "conquest of X" might collide with another war
			//involving "conquest of Y" if the ASCII alphabetics in the province names are identical.
			//While unlikely, this would be quite annoying, so we add in the province ID when a
			//conquest CB is used. TODO: Check this for other CBs eg occupy/retain capital.
			if (war.cb) id += "-" + war.cb.type + "-" + (war.cb.province||"no-province");
			//NOTE: The atk and def counts refer to all players. Even if you aren't interested in
			//wars involving other players but not yourself, they'll still have their "sword" or
			//"shield" indicator given based on any player involvement.
			const atkdef = (war.atk ? "\u{1f5e1}\ufe0f" : "") + (war.def ? "\u{1f6e1}\ufe0f" : "");
			return set_content(DOM("#" + id) || DETAILS({id, open: true}), [
				SUMMARY(atkdef + " " + war.name),
				TABLE({border: "1"}, [
					table_head(["Country", "Infantry", "Cavalry", "Artillery",
						ABBR({title: "Merc infantry"}, "Inf $$"),
						ABBR({title: "Merc cavalry"}, "Cav $$"),
						ABBR({title: "Merc artillery"}, "Art $$"),
						"Total", "Manpower", ABBR({title: "Army professionalism"}, "Prof"),
						ABBR({title: "Army tradition"}, "Trad"),
					]),
					war.armies.map(army => TR({className: army[0].replace(",", "-")}, army.slice(1).map(x => TD(x ? ""+x : "")))),
				]),
				TABLE({border: "1"}, [
					table_head(["Country", "Heavy", "Light", "Galley", "Transport", "Total", "Sailors",
						ABBR({title: "Navy tradition"}, "Trad"),
					]),
					war.navies.map(navy => TR({className: navy[0].replace(",", "-")}, navy.slice(1).map(x => TD(x ? ""+x : "")))),
				]),
			]);
		})]);
	}
	if (state.highlight) {
		if (state.highlight.id) set_content("#expansions", [
			SUMMARY("Building expansions: " + state.highlight.name),
			P("If developed, these places could support a new " + state.highlight.name + ":"),
			TABLE({border: true}, [
				table_head("Province Buildings Devel"),
				state.highlight.provinces.map(prov => TR([
					TD(PROV(prov.id, prov.name)),
					TD(`${prov.buildings}/${prov.maxbuildings}`),
					TD(""+prov.dev),
				])),
			]),
		]);
		else set_content("#expansions", [
			SUMMARY("Building expansions"),
			P("To search for provinces that could be developed to build something, choose a building in" +
			" the top right options."),
		]);
	}
	if (state.buildings_available) set_content("#highlight", [
		SUMMARY("Building highlight"),
		P("Need more of a building? Choose one to highlight places that could be expanded to build it."),
		UL(Object.values(state.buildings_available).map(b => LI(
			state.highlight.id === b.id ? {className: "pickbuilding highlight", "data-bldg": "none"}
				: {className: "pickbuilding", "data-bldg": b.id},
			[`${b.name} (${b.cost})`], //TODO: Add an image if possible
		))),
	]);
}
