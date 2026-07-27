#set page(height: auto, width: auto, margin: 0pt)
#let data = json(bytes(sys.inputs.data))
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
  if x == -100 {
    return table.cell(fill: white, [])
  }
  table.cell(fill: rgb("#0000").mix((green, x/100*5), (red, (1 - x/100)*3)), round(x, digits: 1))
}

#let models = data.map(x => x.at(0))
#let langs = data.filter(x => x.at(0) == "Gemini 3.1 Pro").at(0).at(1).keys()

#table(
  columns: (4.5cm,) + (0.9cm, ) * langs.len(),
  inset: 1pt,
  rows: auto,
  align: (bottom+left,) + (horizon+right, ) * langs.len(),
  stroke: none,
  // table.hline(),
  strong[Model]+v(3pt),
  ..langs.map(x => {
    let (lang1, lang2) = x.split("---")
    lang2 = lang2.replace("Traditional", "Trad.").replace("Simplified", "Simp.")
    strong(rotate(-90deg, reflow: true, box(width: 100pt, align(left, stack(lang1, sym.arrow + lang2, spacing: 4pt)))))}
  ),
  table.hline(),
  ..data.map(x => {
    return (x.at(0), ..langs.map(lang => colored_cell(x.at(1).at(lang))))
  }).flatten(),
  table.hline(),
)