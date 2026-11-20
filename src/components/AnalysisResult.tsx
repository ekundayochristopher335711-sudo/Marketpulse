type AnalysisResultProps = {
  result: { text: string; model: string }
  explanation: string
}

export function AnalysisResult({ result, explanation }: AnalysisResultProps) {
  return <div className="analysis-result"><div className="analysis-result-head"><h4>Analysis</h4><span className="status-pill status-demo">{result.model}</span></div><div className="analysis-text">{result.text}</div><p>{explanation} Confirm observations against source records.</p></div>
}
