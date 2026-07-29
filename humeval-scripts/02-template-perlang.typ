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


#let colored_cell = x => {
  table.cell(fill: luma(300).mix((green, x/100*8), (red, (1 - x/100)*5)), round(x, digits: 1))
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
    let out = (x.at(0), colored_cell(x.at(2)))
    if x.at(3) == "yes" {
      out.push(table.hline(end: 2, stroke: (thickness: 0.5pt, dash: "solid")))
    }
    return out
  }).flatten(),
  table.hline(),
)

#pagebreak()

// TODO: print progress

#let items_len = data.at(0).at(1).len()

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
  rows: (1.3em, auto),
  align: (horizon+left, ) +  (horizon+right, ) * items_len,
  stroke: none,
  table.hline(),
  ..data.map(x => {
    (x.at(0), ) + x.at(1).map(y => colored_tick(y)).flatten()
  }).flatten(),
  table.hline(),
)
