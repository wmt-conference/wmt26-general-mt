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


#let render_model = x => {
  if x.contains(" OPEN") {
    return x.replace(" OPEN", "") + " " + sym.circle.filled
  } else {
    return x
  }
}

#let items_len = 100
#let colored_tick = x => {
  if x == -100 {
    return []
  } else {
    return text(fill: black, sym.square.filled)
  }
}

// overlay for "cold start"
#place(
  top+left,
  dx: 73pt, dy: 0pt,
  box(width: 122pt, height: 217pt, fill: rgb("#ccf"))[
    #set align(center+bottom)
    #text(size: 10pt)[*Cold start phase*]
    #v(2pt)
  ]
)


#table(
  columns: (auto, ) + (5pt, ) * items_len,
  inset: 1pt,
  rows: auto,
  column-gutter: 1pt,
  row-gutter: -2pt,
  align: (horizon+left, ) +  (horizon+right, ) * items_len,
  stroke: none,
  table.hline(),
  ..data.map(x => {
    (text(size: 7pt, render_model(x.model))+h(5pt), ) + x.scores_doc.slice(0, items_len).map(y => colored_tick(y)).flatten()
  }).flatten(),
  table.hline(),
)
#v(0.5cm)


#place(
  bottom+center,
  dx: 100pt, dy: -5pt,
  text(size: 10pt)[*Annotated documents (sequentially left to right)*]
)

#place(
  top+right,
  dx: -50pt, dy: 100pt,
  box(width: auto, height: auto, inset: 5pt, fill: rgb("#aea").transparentize(5%))[
    #set align(center)
    #text(size: 10pt)[*Better models are\ evaluated more often*]
  ]
)