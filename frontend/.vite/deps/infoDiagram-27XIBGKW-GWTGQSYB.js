import {
  parse
} from "./chunk-ESMPGEU5.js";
import "./chunk-KH7G45YE.js";
import "./chunk-HTOXP743.js";
import "./chunk-5IPTFMVQ.js";
import "./chunk-SKGFUYT5.js";
import "./chunk-Q2DHYK5V.js";
import "./chunk-PVZM4SKH.js";
import "./chunk-KQR62P24.js";
import "./chunk-YUSDTILA.js";
import "./chunk-RRU6GFAW.js";
import "./chunk-7RQVZTEQ.js";
import "./chunk-BYNODKYT.js";
import "./chunk-JLVHPIML.js";
import "./chunk-AP3E2UOJ.js";
import "./chunk-2BWK72OE.js";
import "./chunk-RYRQAZW2.js";
import "./chunk-5S2DHMF7.js";
import {
  selectSvgElement
} from "./chunk-AXNCTJKB.js";
import {
  configureSvgSize
} from "./chunk-AS236WFQ.js";
import {
  log
} from "./chunk-LKHU2X6C.js";
import {
  __name
} from "./chunk-UEB47VSI.js";
import "./chunk-PX6F3LHL.js";

// node_modules/mermaid/dist/chunks/mermaid.core/infoDiagram-27XIBGKW.mjs
var parser = {
  parse: __name(async (input) => {
    const ast = await parse("info", input);
    log.debug(ast);
  }, "parse")
};
var DEFAULT_INFO_DB = {
  version: "11.17.2" + (true ? "" : "-tiny")
};
var getVersion = __name(() => DEFAULT_INFO_DB.version, "getVersion");
var db = {
  getVersion
};
var draw = __name((text, id, version) => {
  log.debug("rendering info diagram\n" + text);
  const svg = selectSvgElement(id);
  configureSvgSize(svg, 100, 400, true);
  const group = svg.append("g");
  group.append("text").attr("x", 100).attr("y", 40).attr("class", "version").attr("font-size", 32).style("text-anchor", "middle").text(`v${version}`);
}, "draw");
var renderer = { draw };
var diagram = {
  parser,
  db,
  renderer
};
export {
  diagram
};
//# sourceMappingURL=infoDiagram-27XIBGKW-GWTGQSYB.js.map
