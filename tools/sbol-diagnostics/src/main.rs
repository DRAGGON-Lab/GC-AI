use serde_json::json;
fn main() {
    let path = std::env::args()
        .nth(1)
        .expect("usage: gcai-sbol-diagnostics file.xml");
    let rdf = std::fs::read_to_string(path).expect("read RDF");
    let document = sbol::v3::Document::read(&rdf, sbol::RdfFormat::RdfXml).expect("parse SBOL3");
    let report = match document.check() {
        Ok(r) | Err(r) => r,
    };
    let findings: Vec<_> = report
        .issues()
        .iter()
        .map(|i| {
            json!({
                "severity": format!("{:?}", i.severity).to_lowercase(), "rule_id": i.rule,
                "subject": format!("{}", i.subject), "property": i.property,
                "message": i.message, "hint": format!("{:?}", i.hint)
            })
        })
        .collect();
    println!(
        "{}",
        json!({"validator":"sbol-rs", "version":"0.2.2", "findings":findings,
        "coverage": format!("{:?}", report.coverage()), "options": format!("{:?}", report.options_summary())})
    );
}
