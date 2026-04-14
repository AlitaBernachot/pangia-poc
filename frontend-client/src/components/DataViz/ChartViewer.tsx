// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { DataVizChart } from '../../types'

const PALETTE = [
  '#38bdf8', // sky-400  — bleu ciel vif
  '#1e3a5f', // bleu marine foncé
  '#22d3ee', // cyan-400 — turquoise
  '#0f4c81', // bleu roi profond
  '#7dd3fc', // sky-300  — bleu pâle
  '#0e7490', // cyan-700 — cyan foncé
  '#bae6fd', // sky-200  — bleu très clair
  '#155e75', // cyan-800 — profond
]

interface Props {
  chart: DataVizChart
}

function wrapText(
  selection: d3.Selection<d3.BaseType, unknown, d3.BaseType, unknown>,
  bandwidth: number,
) {
  const maxWidth = Math.max(bandwidth, 30)
  selection.each(function () {
    const text = d3.select(this)
    const words = (text.text() || '').split(/\s+/)
    const x = text.attr('x') ?? 0
    const y = text.attr('y') ?? 0
    const dy = parseFloat(text.attr('dy') ?? '0')
    let line: string[] = []
    let lineNumber = 0
    text.text(null)
    let tspan = text.append('tspan').attr('x', x).attr('y', y).attr('dy', `${dy}em`)
    for (const word of words) {
      line.push(word)
      tspan.text(line.join(' '))
      const node = tspan.node()
      if (node && (node as SVGTextContentElement).getComputedTextLength() > maxWidth) {
        line.pop()
        tspan.text(line.join(' '))
        line = [word]
        lineNumber++
        tspan = text
          .append('tspan')
          .attr('x', x)
          .attr('y', y)
          .attr('dy', `${lineNumber * 1.1 + dy}em`)
          .text(word)
      }
    }
  })
}

export function ChartViewer({ chart }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.innerHTML = ''

    if (chart.chart_type === 'pie') drawPie(el, chart)
    else if (chart.chart_type === 'scatter') drawScatter(el, chart)
    else drawCartesian(el, chart)
  }, [chart])

  return (
    <div className="rounded-xl border border-white/10 bg-white/3 p-4">
      <h3 className="text-sm font-semibold text-white/80 mb-3">{chart.title}</h3>
      <div ref={containerRef} className="w-full" />
    </div>
  )
}

function drawCartesian(el: HTMLElement, chart: DataVizChart) {
  const totalWidth = el.clientWidth || 400
  const margin = { top: 10, right: 20, bottom: 60, left: 50 }
  const width = totalWidth - margin.left - margin.right
  const height = 200 - margin.top - margin.bottom
  const isLine = chart.chart_type === 'line'

  const svg = d3
    .select(el)
    .append('svg')
    .attr('width', totalWidth)
    .attr('height', height + margin.top + margin.bottom)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`)

  const x = d3.scaleBand().domain(chart.labels).range([0, width]).padding(isLine ? 0 : 0.25)

  svg
    .append('g')
    .attr('transform', `translate(0,${height})`)
    .call(d3.axisBottom(x).tickSize(0).tickPadding(8))
    .selectAll('text')
    .attr('fill', 'rgba(255,255,255,0.5)')
    .attr('font-size', '10px')
    .call(wrapText, x.bandwidth())

  svg.select<SVGPathElement>('.domain').attr('stroke', 'rgba(255,255,255,0.15)')

  const allValues = chart.datasets.flatMap((ds) => ds.data as number[])
  const yMax = Math.max(...allValues, 0)
  const y = d3.scaleLinear().domain([0, yMax * 1.1 || 1]).range([height, 0])

  svg
    .append('g')
    .call(d3.axisLeft(y).ticks(4).tickFormat((d) => String(d)))
    .call((g) => g.selectAll('text').attr('fill', 'rgba(255,255,255,0.5)').attr('font-size', '10px'))
    .call((g) => g.selectAll('.domain,.tick line').attr('stroke', 'rgba(255,255,255,0.1)'))

  svg
    .append('g')
    .call(d3.axisLeft(y).ticks(4).tickSize(-width).tickFormat(() => ''))
    .call((g) => g.selectAll('line').attr('stroke', 'rgba(255,255,255,0.06)'))
    .call((g) => g.select('.domain').remove())

  chart.datasets.forEach((ds, dsIdx) => {
    const color = PALETTE[dsIdx % PALETTE.length]
    const data = ds.data as number[]

    if (isLine) {
      const line = d3
        .line<number>()
        .x((_, i) => (x(chart.labels[i]) ?? 0) + x.bandwidth() / 2)
        .y((d) => y(d))
        .curve(d3.curveMonotoneX)

      svg.append('path').datum(data).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2).attr('d', line)

      svg
        .selectAll(`.dot-${dsIdx}`)
        .data(data)
        .enter()
        .append('circle')
        .attr('cx', (_, i) => (x(chart.labels[i]) ?? 0) + x.bandwidth() / 2)
        .attr('cy', (d) => y(d))
        .attr('r', 3)
        .attr('fill', color)
    } else {
      const groupWidth = x.bandwidth() / chart.datasets.length
      svg
        .selectAll(`.bar-${dsIdx}`)
        .data(data)
        .enter()
        .append('rect')
        .attr('x', (_, i) => (x(chart.labels[i]) ?? 0) + dsIdx * groupWidth)
        .attr('y', (d) => y(d))
        .attr('width', Math.max(groupWidth - 2, 1))
        .attr('height', (d) => height - y(d))
        .attr('fill', color)
        .attr('rx', 2)
    }
  })
}

function drawPie(el: HTMLElement, chart: DataVizChart) {
  const totalWidth = el.clientWidth || 320
  const size = Math.min(totalWidth, 260)
  const radius = size / 2 - 10

  const svg = d3
    .select(el)
    .append('svg')
    .attr('width', totalWidth)
    .attr('height', size)
    .append('g')
    .attr('transform', `translate(${totalWidth / 2},${size / 2})`)

  const data = (chart.datasets[0]?.data as number[]) ?? []
  const pie = d3.pie<number>().value((d) => d).sort(null)
  const arc = d3.arc<d3.PieArcDatum<number>>().innerRadius(radius * 0.5).outerRadius(radius)

  svg
    .selectAll('.arc')
    .data(pie(data))
    .enter()
    .append('g')
    .attr('class', 'arc')
    .append('path')
    .attr('d', arc)
    .attr('fill', (_, i) => PALETTE[i % PALETTE.length])
    .attr('stroke', 'rgba(0,0,0,0.3)')
    .attr('stroke-width', 1)

  const legend = d3.select(el).select('svg').append('g').attr('transform', 'translate(10, 10)')
  chart.labels.forEach((lbl, i) => {
    const row = legend.append('g').attr('transform', `translate(0, ${i * 16})`)
    row.append('rect').attr('width', 8).attr('height', 8).attr('y', -8).attr('fill', PALETTE[i % PALETTE.length]).attr('rx', 2)
    row
      .append('text')
      .attr('x', 12)
      .attr('font-size', '9px')
      .attr('fill', 'rgba(255,255,255,0.6)')
      .text(lbl.length > 20 ? lbl.slice(0, 18) + '…' : lbl)
  })
}

function drawScatter(el: HTMLElement, chart: DataVizChart) {
  const totalWidth = el.clientWidth || 400
  const margin = { top: 10, right: 20, bottom: 40, left: 50 }
  const width = totalWidth - margin.left - margin.right
  const height = 200 - margin.top - margin.bottom

  const svg = d3
    .select(el)
    .append('svg')
    .attr('width', totalWidth)
    .attr('height', height + margin.top + margin.bottom)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`)

  const allPoints = chart.datasets.flatMap((ds) => ds.data as { x: number; y: number }[])
  const xExt = d3.extent(allPoints, (p) => p.x) as [number, number]
  const yExt = d3.extent(allPoints, (p) => p.y) as [number, number]

  const x = d3.scaleLinear().domain(xExt).nice().range([0, width])
  const y = d3.scaleLinear().domain(yExt).nice().range([height, 0])

  svg
    .append('g')
    .attr('transform', `translate(0,${height})`)
    .call(d3.axisBottom(x).ticks(5).tickFormat((d) => String(d)))
    .call((g) => g.selectAll('text').attr('fill', 'rgba(255,255,255,0.5)').attr('font-size', '10px'))
    .call((g) => g.selectAll('.domain,.tick line').attr('stroke', 'rgba(255,255,255,0.1)'))

  svg
    .append('g')
    .call(d3.axisLeft(y).ticks(5).tickFormat((d) => String(d)))
    .call((g) => g.selectAll('text').attr('fill', 'rgba(255,255,255,0.5)').attr('font-size', '10px'))
    .call((g) => g.selectAll('.domain,.tick line').attr('stroke', 'rgba(255,255,255,0.1)'))

  chart.datasets.forEach((ds, dsIdx) => {
    const color = PALETTE[dsIdx % PALETTE.length]
    const points = ds.data as { x: number; y: number }[]
    svg
      .selectAll(`.dot-${dsIdx}`)
      .data(points)
      .enter()
      .append('circle')
      .attr('cx', (d) => x(d.x))
      .attr('cy', (d) => y(d.y))
      .attr('r', 4)
      .attr('fill', color)
      .attr('fill-opacity', 0.75)
  })
}
