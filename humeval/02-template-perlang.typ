#set page(height: 12cm, width: auto, margin: 0pt)
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

#let render_model = x => {
  if x.contains(" OPEN") {
    return x.replace(" OPEN", "") + " " + sym.circle.filled
  } else {
    return x
  }
}

#let (lang1, lang2) = (
  langs
      .replace("Traditional Chinese", "Chinese (Trad.)")
      .replace("Simplified Chinese", "Chinese (Simp.)")
      .split("---")
)

#table(
  columns: (4.5cm, 0.8cm, 0.3cm),
  inset: 1pt,
  rows: (1.3em, 1em),
  align: (horizon+left, horizon+right, horizon+right),
  stroke: none,
  table.hline(),
  strong(lang1 + sym.arrow + lang2+h(-1cm)),
  if lang2 != "Japanese" { align(left, text(size: 5pt)[*Score*])} else {},
  text(size: 5pt)[*Docs*],
  table.hline(),
  ..data.map(x => {
    let out = (
      render_model(x.model),
      colored_cell(x.scores_mean),
      text(size: 5pt, 
        str(x.scores_doc.filter(y => y != -100).len()),
      // stack(
      //   str(x.scores_seg.filter(y => y != -100).len()),
      //   spacing: 2pt,
      // )
      ),
    )
    if x.cluster == "yes_cluster" {
      out.push(table.hline(
        end: 1,
        stroke: (thickness: 0.5pt, paint: luma(0), dash: (110pt, 5000pt))
      ))
    } else if x.cluster == "yes_local" {
      out.push(table.hline(
        end: 1,
        stroke: (thickness: 0.5pt, paint: luma(150), dash: (60pt, 5000pt))
      ))
    }
    return out
  }).flatten(),
  table.hline(),
)