#set page(height: auto, width: auto, margin: 0pt)
#let data = json(bytes(sys.inputs.data))
#let langs = json(bytes(sys.inputs.langs))
// LaTeX ACL font
#set text(font: "New Computer Modern", size: 10pt)

#let round(x, digits: 2) = {
  if digits == 0 { return str(calc.round(x, digits: 0)) }
  
  let s = str(calc.round(x, digits: digits))
  let parts = s.split(".")
  
  if parts.len() == 1 {
    parts.push("")
  }
  
  parts.at(0) + "." + parts.at(1) + "0" * (digits - parts.at(1).len())
}


#let items_len = data.at(0).scores_doc.len()
#let colored_tick = x => {
  if x == -100 {
    return table.cell(fill: luma(200).mix(red), [])
  } else {
    return table.cell(fill: luma(200).mix(green), [])
  }
}

#table(
  columns: (4.5cm, ) + (10pt, ) * items_len,
  inset: 1pt,
  rows: auto,
  align: (horizon+left, ) +  (horizon+right, ) * items_len,
  stroke: none,
  table.hline(),
  ..data.map(x => {
    (x.model, ) + x.scores_doc.map(y => colored_tick(y)).flatten()
  }).flatten(),
  table.hline(),
)
