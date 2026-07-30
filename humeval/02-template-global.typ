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
    return table.cell(fill: luma(200), [])
  }
  table.cell(fill: luma(300).mix((green, x/100*8), (red, (1 - x/100)*5)), round(x, digits: 1))
}

#let models = data.map(x => x.at(0))
#let langs = data.filter(x => x.at(0) == "Gemini 3.1 Pro").at(0).at(1).keys()

#let render_model = x => {
  if x.contains(" OPEN") {
    return x.replace(" OPEN", "") + " " + sym.circle.filled
  } else {
    return x
  }
}

#table(
  columns: (4.5cm,) + (0.8cm, ) * langs.len(),
  inset: 1pt,
  rows: auto,
  align: (bottom+left,) + (horizon+right, ) * langs.len(),
  stroke: none,
  // table.hline(),
  strong[Model]+v(3pt),
  ..langs.map(x => {
    let (lang1, lang2) = (
      x
      .replace("Traditional Chinese", "Chinese (Trad.)")
      .replace("Simplified Chinese", "Chinese (Simp.)")
      .split("---")
    )
    align(bottom+center, strong(rotate(-90deg, reflow: true, lang1 + sym.arrow + lang2)))}
  ),
  table.hline(),
  ..data.map(x => {
    return (render_model(x.at(0)), ..langs.map(lang => colored_cell(x.at(1).at(lang))))
  }).flatten(),
  table.hline(),
)