import {
  db,
  getStyles,
  renderer
} from "./chunk-UWDOADBB.js";
import {
  populateCommonDb
} from "./chunk-MBDTP6V4.js";
import {
  MermaidParseError
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
import {
  createRailroadServices
} from "./chunk-7RQVZTEQ.js";
import "./chunk-BYNODKYT.js";
import "./chunk-JLVHPIML.js";
import "./chunk-AP3E2UOJ.js";
import "./chunk-2BWK72OE.js";
import "./chunk-RYRQAZW2.js";
import "./chunk-5S2DHMF7.js";
import "./chunk-AXNCTJKB.js";
import "./chunk-AS236WFQ.js";
import {
  log
} from "./chunk-LKHU2X6C.js";
import {
  __name
} from "./chunk-UEB47VSI.js";
import "./chunk-PX6F3LHL.js";

// node_modules/mermaid/dist/chunks/mermaid.core/railroadDiagram-O6MQD6OU.mjs
var langiumParser = createRailroadServices().Railroad.parser.LangiumParser;
var transformExpression = __name((expr) => {
  switch (expr.$type) {
    case "RailroadTerminalExpr":
      return {
        type: "terminal",
        value: expr.value
      };
    case "RailroadNonTerminalExpr":
      return {
        type: "nonterminal",
        name: expr.name
      };
    case "RailroadSpecialExpr":
      return {
        type: "special",
        text: expr.text
      };
    case "RailroadSequenceExpr": {
      const elements = expr.elements.map(transformExpression);
      return elements.length === 1 ? elements[0] : { type: "sequence", elements };
    }
    case "RailroadChoiceExpr": {
      const alternatives = expr.alternatives.map(transformExpression);
      return alternatives.length === 1 ? alternatives[0] : { type: "choice", alternatives };
    }
    case "RailroadOptionalExpr":
      return {
        type: "optional",
        element: transformExpression(expr.element)
      };
    case "RailroadOneOrMoreExpr":
      return {
        type: "repetition",
        element: transformExpression(expr.element),
        min: 1,
        max: Infinity
      };
    case "RailroadZeroOrMoreExpr":
      return {
        type: "repetition",
        element: transformExpression(expr.element),
        min: 0,
        max: Infinity
      };
    default:
      throw new Error(`Unsupported railroad expression: ${expr.$type}`);
  }
}, "transformExpression");
var transformRule = __name((rule) => {
  return {
    name: rule.name,
    definition: transformExpression(rule.definition)
  };
}, "transformRule");
var populateDb = __name((ast) => {
  populateCommonDb(ast, db);
  if (ast.title) {
    db.setTitle(ast.title);
  }
  ast.rules.map((rule) => db.addRule(transformRule(rule)));
}, "populateDb");
var parser = {
  parse: __name((input) => {
    db.clear();
    log.debug("[Railroad Parser] Starting Langium parse");
    const result = langiumParser.parse(input);
    if (result.lexerErrors.length > 0 || result.parserErrors.length > 0) {
      throw new MermaidParseError(result);
    }
    const ast = result.value;
    log.debug("[Railroad Parser] Parsed rules:", ast.rules.length);
    populateDb(ast);
    log.debug("[Railroad Parser] Parse complete");
  }, "parse"),
  parser: {
    yy: db
  }
};
var diagram = {
  parser,
  db,
  renderer,
  styles: getStyles
};
var railroadDiagram_default = diagram;
export {
  railroadDiagram_default as default,
  diagram
};
//# sourceMappingURL=railroadDiagram-O6MQD6OU-4TTJID5M.js.map
