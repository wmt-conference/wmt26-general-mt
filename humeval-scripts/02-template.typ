#set page(height: auto, width: auto, margin: 0pt)
#let data = json(bytes(sys.inputs.data))
#let langs = json(bytes(sys.inputs.langs))
// LaTeX ACL font
#set text(font: "New Computer Modern", size: 10pt)

#let colored_cell = x => {
  let x_float = float(x)
  table.cell(fill: rgb("#0000").mix((green, x_float/100*5), (red, 1 - x_float/100)), x)
}

#table(
  columns: (4.5cm, 0.8cm),
  inset: 1pt,
  rows: (1.3em, auto),
  align: (horizon+left, horizon+right),
  stroke: none,
  table.hline(),
  strong(langs.at(0) + sym.arrow + langs.at(1)), [*Score*],
  table.hline(),
  ..data.map(x => {
    let out = (x.at(0), colored_cell(x.at(1)))
    if x.at(2) == "yes" {
      out.push(table.hline(end: 2, stroke: (thickness: 0.5pt, dash: "solid")))
    }
    return out
  }).flatten(),
  table.hline(),
)