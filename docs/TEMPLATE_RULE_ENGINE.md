# Template rule engine

`TemplateRuleEngine` deterministically intersects certified page evidence with mapped regions, applies page policies, ignores excluded regions, resolves controlled anchors, maps repeating tables, classifies rows and preserves each tax row. Field outputs retain their source. Derived fields are explicitly marked and retain their input names instead of claiming a source box.

Transforms are a whitelist. Formulas use a restricted arithmetic syntax tree supporting numeric constants, named inputs, unary signs and `+ - * /`; calls, attributes, subscripts and arbitrary code are prohibited. There is no `eval()`.
