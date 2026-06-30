---
name: Chart Visualization
description: This skill should be used when the user wants to visualize data. It intelligently selects the most suitable chart type from 26 available options, extracts parameters based on detailed specifications, and generates chart visualizations.
---

# Chart Visualization Skill

This skill provides a comprehensive workflow for transforming data into visual charts. It handles chart selection, parameter extraction, and chart generation.

## Workflow

To visualize data, follow these steps:

### 1. Intelligent Chart Selection
Analyze the user's data features to determine the most appropriate chart type:

- **Time Series**: Line chart (trends), Area chart (accumulated trends), Dual-axis chart (two different scales)
- **Comparisons**: Bar chart (categorical), Column chart (vertical bars), Histogram (distribution), Boxplot (statistical summary), Violin chart (density distribution)
- **Part-to-Whole**: Pie chart, Funnel chart, Treemap, Liquid chart (single value progress)
- **Relationships**: Scatter chart, Radar chart, Venn diagram
- **Maps**: District map (administrative regions), Path map (routes/trajectories), Pin map (point markers)
- **Hierarchies**: Organization chart, Mind map, Flow diagram, Sankey diagram, Network graph
- **Specialized**: Fishbone diagram (cause-effect), Word cloud, Spreadsheet (tabular display)

### 2. Data Preparation
Ensure data is properly structured for the chosen chart type:
- Include all necessary values (labels, numbers, categories)
- Format data as JSON arrays or key-value objects
- Handle missing or null values appropriately

### 3. Chart Generation
Generate the chart using available visualization tools:
- For HTML-based output: Use Chart.js, D3.js, or ECharts libraries in a standalone HTML file
- For image-based output: Generate using canvas-based rendering
- For spreadsheet-like display: Use HTML tables with styling

### 4. Output
- Embed charts in a self-contained HTML workspace output
- Include clear titles, labels, and legends
- Support responsive sizing
- Use color palettes that are accessible and visually appealing

## Chart Selection Guidelines

| User Need | Recommended Chart |
|-----------|-------------------|
| Show trend over time | Line, Area |
| Compare values across categories | Bar, Column |
| Show distribution | Histogram, Boxplot, Violin |
| Show parts of a whole | Pie, Treemap, Funnel |
| Show correlation | Scatter |
| Show multi-variable comparison | Radar |
| Show flow / process | Sankey, Flow Diagram |
| Show hierarchy | Org Chart, Mind Map, Treemap |
| Show geographic data | District Map, Pin Map, Path Map |
| Show root cause | Fishbone Diagram |
| Show overlap / intersection | Venn Diagram |
| Show text frequency | Word Cloud |
| Show tabular data | Spreadsheet |

## Design Principles

- Use accessible color palettes with sufficient contrast
- Include clear axis labels and legends
- Add context through titles and subtitles
- Support interactive tooltips when possible
- Ensure responsive design for various screen sizes
