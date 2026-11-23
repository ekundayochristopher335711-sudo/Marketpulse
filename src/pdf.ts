import { jsPDF } from 'jspdf'
import { autoTable } from 'jspdf-autotable'
import { median, orderedListings } from './intelligence'
import type { Product } from './types'

const navy: [number, number, number] = [24, 39, 62]
const blue: [number, number, number] = [55, 105, 217]
const muted: [number, number, number] = [99, 113, 134]
const pdfRowBatchSize = 1_000
const cash = (value: number) => `NGN ${value.toLocaleString('en-NG')}`
const clean = (value: string) => value.replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"').replace(/[\u2013\u2014]/g, '-').replace(/\u20a6/g, 'NGN ').replace(/[\r\n\t]+/g, ' ')

export function createMarketPdf(products: Product[], datasetLabel: string): jsPDF {
  if (!products.length) throw new Error('There are no records to export yet.')
  const rows = orderedListings(products)
  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4', compress: true })
  const width = doc.internal.pageSize.getWidth()
  const height = doc.internal.pageSize.getHeight()
  const generated = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Lagos' }).format(new Date())
  doc.setProperties({ title: 'MarketPulse Nigeria - Market report', subject: datasetLabel, author: 'MarketPulse', creator: 'MarketPulse' })

  doc.setFillColor(...navy)
  doc.rect(0, 0, width, 50, 'F')
  doc.setFont('helvetica', 'bold')
  doc.setTextColor(255, 255, 255)
  doc.setFontSize(10)
  doc.text('MARKETPULSE / NIGERIA', 14, 14)
  doc.setFontSize(24)
  doc.text('Market report', 14, 29)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9)
  doc.text(doc.splitTextToSize(clean(datasetLabel), width - 28).slice(0, 2), 14, 40)
  doc.text(`${generated} WAT`, width - 14, 14, { align: 'right' })

  const metrics = [
    ['Listing records', rows.length.toLocaleString('en-NG')],
    ['Median asking price', cash(median(rows.map(row => row.price)))],
    ['Sources represented', String(new Set(rows.map(row => row.source)).size)],
  ]
  metrics.forEach(([label, value], index) => {
    const x = 14 + index * 91
    doc.setFillColor(242, 246, 252)
    doc.roundedRect(x, 58, 87, 24, 2, 2, 'F')
    doc.setTextColor(...muted)
    doc.setFontSize(8)
    doc.text(label, x + 5, 66)
    doc.setTextColor(...navy)
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(14)
    doc.text(value, x + 5, 76)
    doc.setFont('helvetica', 'normal')
  })
  doc.setTextColor(...navy)
  doc.setFontSize(12)
  doc.text('Category summary', 14, 94)
  const grouped = new Map<string, Product[]>()
  rows.forEach(row => {
    const categoryRows = grouped.get(row.category)
    if (categoryRows) categoryRows.push(row)
    else grouped.set(row.category, [row])
  })
  const categories = [...grouped].sort((left, right) => right[1].length - left[1].length || left[0].localeCompare(right[0])).slice(0, 16)
  for (let part = 0; part < 2; part++) {
    const segment = categories.slice(part * 8, part * 8 + 8)
    if (!segment.length) continue
    autoTable(doc, {
      startY: 100,
      tableWidth: 130,
      head: [['Category', 'Records', 'Median ask']],
      body: segment.map(([category, items]) => [clean(category), items.length, cash(median(items.map(item => item.price)))]),
      margin: { left: part ? 153 : 14, top: 30, bottom: 23 },
      theme: 'striped',
      styles: { font: 'helvetica', fontSize: 8, cellPadding: 2.2, textColor: navy, overflow: 'linebreak' },
      headStyles: { fillColor: blue, textColor: 255 },
      columnStyles: { 0: { cellWidth: 64 }, 1: { cellWidth: 19, halign: 'right' }, 2: { cellWidth: 47, halign: 'right' } },
    })
  }
  if (grouped.size > 16) {
    doc.setFontSize(8)
    doc.setTextColor(...muted)
    doc.text(`Showing the 16 largest of ${grouped.size} categories. Every exported record appears in the listing tables.`, 14, height - 26)
  }

  doc.addPage()
  for (let offset = 0; offset < rows.length; offset += pdfRowBatchSize) {
    if (offset > 0) doc.addPage()
    const batch = rows.slice(offset, offset + pdfRowBatchSize)
    autoTable(doc, {
      startY: 33,
      head: [['#', 'Product / category', 'Asking price', 'Location', 'Source / condition', 'Last observed (WAT)']],
      body: batch.map((row, index) => {
        const observed = row.observedAt ? new Date(row.observedAt) : null
        const stamp = observed && !Number.isNaN(observed.valueOf())
          ? new Intl.DateTimeFormat('en-GB', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Africa/Lagos' }).format(observed)
          : row.listed
        return [offset + index + 1, `${clean(row.title)}\n${clean(row.category)}`, cash(row.price), clean(row.location), `${clean(row.source)}\n${clean(row.condition)}`, clean(stamp)]
      }),
      theme: 'striped',
      margin: { top: 33, bottom: 23, left: 14, right: 14 },
      styles: { font: 'helvetica', fontSize: 8, cellPadding: 3, textColor: navy, overflow: 'linebreak', valign: 'top' },
      headStyles: { fillColor: navy, textColor: 255 },
      alternateRowStyles: { fillColor: [245, 248, 252] },
      rowPageBreak: 'avoid',
      columnStyles: { 0: { cellWidth: 11 }, 1: { cellWidth: 85 }, 2: { cellWidth: 35, halign: 'right' }, 3: { cellWidth: 44 }, 4: { cellWidth: 51 }, 5: { cellWidth: 43 } },
      didDrawCell: data => {
        if (data.section !== 'body' || data.column.index !== 1) return
        const url = batch[data.row.index]?.sourceUrl
        if (url && /^https?:\/\//i.test(url)) doc.link(data.cell.x, data.cell.y, data.cell.width, data.cell.height, { url })
      },
    })
  }

  const pages = doc.getNumberOfPages()
  for (let page = 1; page <= pages; page++) {
    doc.setPage(page)
    if (page > 1) {
      doc.setFont('helvetica', 'bold')
      doc.setFontSize(12)
      doc.setTextColor(...navy)
      doc.text('MarketPulse / Listing records', 14, 15)
      doc.setFont('helvetica', 'normal')
      doc.setFontSize(8)
      doc.setTextColor(...muted)
      doc.text('Ordered by category, then product name. Product names link to source pages when available.', 14, 23)
    }
    doc.setDrawColor(220, 227, 237)
    doc.line(14, height - 17, width - 14, height - 17)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7)
    doc.setTextColor(...muted)
    doc.text('Asking prices are not sale prices. Listing volume does not prove buyer demand. Verify each source before relying on a record.', 14, height - 11)
    doc.text(`${generated} WAT | ${page} / ${pages}`, width - 14, height - 6, { align: 'right' })
  }
  return doc
}

export function downloadMarketPdf(products: Product[], datasetLabel: string, filename: string): void {
  createMarketPdf(products, datasetLabel).save(filename)
}
