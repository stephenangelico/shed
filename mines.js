let width = 10, height = 10, mines = 10;
const game = [];

function set_content(elem, children) {
	while (elem.lastChild) elem.removeChild(elem.lastChild);
	if (!Array.isArray(children)) children = [children];
	for (let child of children) {
		if (child === "") continue;
		if (typeof child === "string") child = document.createTextNode(child);
		elem.appendChild(child);
	}
	return elem;
}
function build(tag, attributes, children) {
	const ret = document.createElement(tag);
	if (attributes) for (let attr in attributes) {
		if (attr.startsWith("data-")) //Simplistic - we don't transform "data-foo-bar" into "fooBar" per HTML.
			ret.dataset[attr.slice(5)] = attributes[attr];
		else ret[attr] = attributes[attr];
	}
	if (children) set_content(ret, children);
	return ret;
}

function clicked(ev) {
	const btn = ev.currentTarget;
	console.log("Clicked", btn.dataset.x, btn.dataset.y);
}

function new_game() {
	const board = document.getElementById("board");
	const table = [];
	for (let y = 0; y < height; ++y) {
		const row = [], tr = [];
		for (let x = 0; x < width; ++x) {
			row.push(0);
			tr.push(build("td", 0, build("button", {"data-x": x, "data-y": y, onclick: clicked})));
		}
		game.push(row);
		table.push(build("tr", 0, tr));
	}
	set_content(board, table);
}

new_game();
