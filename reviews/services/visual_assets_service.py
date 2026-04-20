import json
import os
from itertools import combinations
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from reviews.models import Paper, Review, SearchQuery
import pycountry


class VisualAssetsService:
    stage_key = 'phase_22_visual_assets'
    title_font_family = 'Times New Roman, Georgia, serif'
    body_font_family = 'Arial, Helvetica, sans-serif'
    color_primary = '#1f4e79'
    color_secondary = '#0f766e'
    color_accent = '#2563eb'
    color_text = '#0f172a'
    color_grid = 'rgba(148,163,184,0.22)'
    color_header_bg = '#1f4e79'
    color_header_text = '#ffffff'
    color_table_bg = '#f8fafc'
    color_table_alt = '#eef4fb'

    def __init__(self, review_id):
        self.review = Review.objects.get(pk=review_id)
        self.assets_dir = Path(settings.MEDIA_ROOT) / 'visual_assets' / str(self.review.id)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def _apply_figure_layout(self, fig, title_text, height=760, margin=None, showlegend=False):
        fig.update_layout(
            title={
                'text': title_text,
                'x': 0.01,
                'xanchor': 'left',
                'font': {'family': self.title_font_family, 'size': 24, 'color': self.color_text},
            },
            template='plotly_white',
            plot_bgcolor='#ffffff',
            paper_bgcolor='#ffffff',
            font={'family': self.body_font_family, 'size': 13, 'color': self.color_text},
            margin=margin or {'l': 80, 'r': 40, 't': 90, 'b': 70},
            showlegend=showlegend,
            height=height,
        )

    def _table_header(self, values):
        return {
            'values': values,
            'fill_color': self.color_header_bg,
            'font': {'color': self.color_header_text, 'size': 12, 'family': self.body_font_family},
            'align': 'left',
            'line_color': '#d7e2ee',
            'height': 32,
        }

    def _table_cells(self, values, height=27):
        row_count = len(values[0]) if values and values[0] is not None else 0
        fills = []
        for _ in values:
            col = [self.color_table_bg if i % 2 == 0 else self.color_table_alt for i in range(row_count)]
            fills.append(col)
        return {
            'values': values,
            'fill_color': fills,
            'align': 'left',
            'font': {'size': 11, 'family': self.body_font_family, 'color': self.color_text},
            'line_color': '#e2e8f0',
            'height': height,
        }
    def generate(self, bundle='all'):
        generated = []

        if bundle in {'all', 'core'}:
            generated.extend(self._generate_keyword_cooccurrence_network())
            generated.extend(self._generate_thematic_map_2x2())
            generated.extend(self._generate_geographic_choropleth())
            generated.extend(self._generate_temporal_trend())
            generated.extend(self._generate_keyword_top_terms_bar())
            generated.extend(self._generate_journal_impact())
            generated.extend(self._generate_study_characteristics_table())
            generated.extend(self._generate_tccm_analysis_table())
            generated.extend(self._generate_quality_assessment_table())
            generated.extend(self._generate_scopus_query_strings_table())
            generated.extend(self._generate_pico_and_criteria_table())

        if bundle in {'all', 'evidence'}:
            generated.extend(self._generate_thematic_crosstab())
            generated.extend(self._generate_evidence_strength_heatmap())

        if bundle in {'all', 'admin'}:
            generated.extend(self._generate_prisma_payload())
            generated.extend(self._generate_prisma_flow_diagram())
            generated.extend(self._generate_cleaning_summary())

        self._persist_stage(generated=generated, bundle=bundle)
        return {'generated': generated, 'bundle': bundle}

    def list_assets(self):
        files = []
        if not self.assets_dir.exists():
            return files
        for fp in sorted(self.assets_dir.iterdir()):
            if fp.is_file():
                rel = fp.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
                files.append(
                    {
                        'name': fp.name,
                        'relative_path': rel,
                        'url': f"{settings.MEDIA_URL}{rel}",
                        'size_kb': round(fp.stat().st_size / 1024.0, 1),
                    }
                )
        return files

    def _generate_keyword_cooccurrence_network(self):
        papers = list(self.review.papers.exclude(keywords='').values_list('keywords', flat=True))
        if not papers:
            return []

        keyword_counter = Counter()
        edge_counter = Counter()

        for raw in papers:
            tokens = self._normalize_keywords(raw)
            if len(tokens) < 1:
                continue
            unique_tokens = sorted(set(tokens))
            for kw in unique_tokens:
                keyword_counter[kw] += 1
            if len(unique_tokens) >= 2:
                for a, b in combinations(unique_tokens, 2):
                    edge_counter[(a, b)] += 1

        if not keyword_counter:
            return []

        top_terms = {k for k, _ in keyword_counter.most_common(40)}
        filtered_edges = {
            pair: w for pair, w in edge_counter.items()
            if pair[0] in top_terms and pair[1] in top_terms and w >= 2
        }

        if not filtered_edges:
            return []

        try:
            import networkx as nx
            import plotly.graph_objects as go

            g = nx.Graph()
            for kw in top_terms:
                g.add_node(kw, freq=keyword_counter.get(kw, 1))
            for (a, b), w in filtered_edges.items():
                g.add_edge(a, b, weight=w)

            # Keep largest connected component for clarity
            if g.number_of_nodes() > 0 and g.number_of_edges() > 0:
                largest_nodes = max(nx.connected_components(g), key=len)
                g = g.subgraph(largest_nodes).copy()

            pos = nx.spring_layout(g, k=0.85, iterations=250, seed=42, weight='weight')

            nodes = []
            for n in g.nodes():
                nodes.append(
                    {
                        'id': n,
                        'x': float(pos[n][0]),
                        'y': float(pos[n][1]),
                        'frequency': int(g.nodes[n].get('freq', 1)),
                        'degree': int(g.degree(n)),
                    }
                )

            edges = []
            for u, v, data in g.edges(data=True):
                edges.append({'source': u, 'target': v, 'weight': int(data.get('weight', 1))})

            out_json = self.assets_dir / 'figure_keyword_cooccurrence_network.json'
            out_json.write_text(
                json.dumps({'nodes': nodes, 'edges': edges}, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
            generated = [out_json.name]

            edge_x = []
            edge_y = []
            for u, v, data in g.edges(data=True):
                x0, y0 = pos[u]
                x1, y1 = pos[v]
                edge_x.extend([x0, x1, None])
                edge_y.extend([y0, y1, None])

            edge_trace = go.Scatter(
                x=edge_x,
                y=edge_y,
                line={'width': 0.6, 'color': 'rgba(100,116,139,0.45)'},
                hoverinfo='none',
                mode='lines',
            )

            node_x = [pos[n][0] for n in g.nodes()]
            node_y = [pos[n][1] for n in g.nodes()]
            node_text = []
            node_size = []
            node_color = []
            for n in g.nodes():
                freq = int(g.nodes[n].get('freq', 1))
                deg = int(g.degree(n))
                node_text.append(f"{n}<br>Frequency: {freq}<br>Degree: {deg}")
                node_size.append(8 + min(freq * 2.2, 26))
                node_color.append(deg)

            label_x = []
            label_y = []
            label_text = []
            for n in sorted(g.nodes(), key=lambda x: g.nodes[x].get('freq', 1), reverse=True)[:20]:
                label_x.append(pos[n][0])
                label_y.append(pos[n][1])
                label_text.append(n)

            node_trace = go.Scatter(
                x=node_x,
                y=node_y,
                mode='markers',
                text=node_text,
                hoverinfo='text',
                marker={
                    'showscale': True,
                    'colorscale': 'Viridis',
                    'color': node_color,
                    'size': node_size,
                    'line': {'width': 1, 'color': '#ffffff'},
                    'colorbar': {'title': 'Node Degree'},
                    'opacity': 0.92,
                },
            )

            label_trace = go.Scatter(
                x=label_x,
                y=label_y,
                mode='text',
                text=label_text,
                textposition='top center',
                textfont={'family': 'Arial', 'size': 11, 'color': '#0f172a'},
                hoverinfo='none',
            )

            fig = go.Figure(data=[edge_trace, node_trace, label_trace])
            fig.update_layout(
                title={
                    'text': 'Keyword Co-occurrence Network',
                    'x': 0.01,
                    'xanchor': 'left',
                    'font': {'family': self.title_font_family, 'size': 24, 'color': self.color_text},
                },
                showlegend=False,
                hovermode='closest',
                margin={'b': 20, 'l': 20, 'r': 20, 't': 70},
                template='plotly_white',
                paper_bgcolor='#ffffff',
                plot_bgcolor='#ffffff',
                xaxis={'showgrid': False, 'zeroline': False, 'visible': False},
                yaxis={'showgrid': False, 'zeroline': False, 'visible': False},
                font={'family': 'Arial', 'size': 13, 'color': '#0f172a'},
            )

            html_path = self.assets_dir / 'figure_keyword_cooccurrence_network.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)

            return generated
        except Exception:
            return []

    def _generate_thematic_map_2x2(self):
        papers = list(self.review.papers.exclude(keywords='').values_list('keywords', flat=True))
        if not papers:
            return []

        keyword_counter = Counter()
        edge_counter = Counter()
        for raw in papers:
            tokens = self._normalize_keywords(raw)
            if not tokens:
                continue
            unique_tokens = sorted(set(tokens))
            for kw in unique_tokens:
                keyword_counter[kw] += 1
            if len(unique_tokens) >= 2:
                for a, b in combinations(unique_tokens, 2):
                    edge_counter[(a, b)] += 1

        if not keyword_counter:
            return []

        top_terms = {k for k, _ in keyword_counter.most_common(60)}
        filtered_edges = {
            pair: w for pair, w in edge_counter.items()
            if pair[0] in top_terms and pair[1] in top_terms and w >= 2
        }
        if not filtered_edges:
            return []

        try:
            import networkx as nx
            import plotly.graph_objects as go

            g = nx.Graph()
            for kw in top_terms:
                g.add_node(kw, freq=keyword_counter.get(kw, 1))
            for (a, b), w in filtered_edges.items():
                g.add_edge(a, b, weight=w)

            if g.number_of_nodes() == 0 or g.number_of_edges() == 0:
                return []

            # Focus on largest connected component
            largest_nodes = max(nx.connected_components(g), key=len)
            g = g.subgraph(largest_nodes).copy()

            communities = []
            try:
                communities = list(nx.community.louvain_communities(g, weight='weight', seed=42))
            except Exception:
                communities = list(nx.community.greedy_modularity_communities(g, weight='weight'))

            if not communities:
                return []

            records = []
            for i, comm in enumerate(communities, start=1):
                nodes = list(comm)
                if len(nodes) < 2:
                    continue
                sub = g.subgraph(nodes)

                internal_weight = 0.0
                for _, _, data in sub.edges(data=True):
                    internal_weight += float(data.get('weight', 1.0))
                possible_internal = max((len(nodes) * (len(nodes) - 1)) / 2.0, 1.0)
                density = internal_weight / possible_internal

                external_weight = 0.0
                for n in nodes:
                    for nbr, data in g[n].items():
                        if nbr not in comm:
                            external_weight += float(data.get('weight', 1.0))
                centrality = external_weight / max(len(nodes), 1)

                top_keywords = sorted(nodes, key=lambda x: keyword_counter.get(x, 0), reverse=True)[:4]
                label = ', '.join(top_keywords)

                records.append(
                    {
                        'cluster_id': i,
                        'label': label,
                        'keywords': top_keywords,
                        'size': len(nodes),
                        'density': round(density, 4),
                        'centrality': round(centrality, 4),
                        'total_keyword_frequency': int(sum(keyword_counter.get(k, 0) for k in nodes)),
                    }
                )

            if not records:
                return []

            x_vals = [r['centrality'] for r in records]
            y_vals = [r['density'] for r in records]
            x_mid = sorted(x_vals)[len(x_vals) // 2]
            y_mid = sorted(y_vals)[len(y_vals) // 2]

            for r in records:
                if r['centrality'] >= x_mid and r['density'] >= y_mid:
                    quad = 'Motor Themes'
                elif r['centrality'] < x_mid and r['density'] >= y_mid:
                    quad = 'Niche Themes'
                elif r['centrality'] < x_mid and r['density'] < y_mid:
                    quad = 'Emerging/Declining Themes'
                else:
                    quad = 'Basic Themes'
                r['quadrant'] = quad

            out_json = self.assets_dir / 'figure_thematic_map_2x2.json'
            out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
            generated = [out_json.name]

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=y_vals,
                    mode='markers+text',
                    text=[f"C{r['cluster_id']}" for r in records],
                    textposition='top center',
                    marker={
                        'size': [12 + min(r['size'] * 2.8, 26) for r in records],
                        'color': [r['total_keyword_frequency'] for r in records],
                        'colorscale': 'Viridis',
                        'line': {'width': 1, 'color': '#ffffff'},
                        'showscale': True,
                        'colorbar': {'title': 'Total Keyword Freq'},
                        'opacity': 0.92,
                    },
                    hovertext=[
                        f"Cluster {r['cluster_id']}<br>Label: {r['label']}<br>Centrality: {r['centrality']}<br>Density: {r['density']}<br>Quadrant: {r['quadrant']}"
                        for r in records
                    ],
                    hoverinfo='text',
                )
            )

            fig.add_vline(x=x_mid, line={'color': '#64748b', 'width': 1.5, 'dash': 'dash'})
            fig.add_hline(y=y_mid, line={'color': '#64748b', 'width': 1.5, 'dash': 'dash'})

            fig.add_annotation(x=max(x_vals), y=max(y_vals), xanchor='right', yanchor='top', text='Motor Themes', showarrow=False, font={'size': 12, 'color': '#0f172a'})
            fig.add_annotation(x=min(x_vals), y=max(y_vals), xanchor='left', yanchor='top', text='Niche Themes', showarrow=False, font={'size': 12, 'color': '#0f172a'})
            fig.add_annotation(x=min(x_vals), y=min(y_vals), xanchor='left', yanchor='bottom', text='Emerging/Declining', showarrow=False, font={'size': 12, 'color': '#0f172a'})
            fig.add_annotation(x=max(x_vals), y=min(y_vals), xanchor='right', yanchor='bottom', text='Basic Themes', showarrow=False, font={'size': 12, 'color': '#0f172a'})

            fig.update_layout(
                title={
                    'text': 'Thematic Map (Centrality vs Density)',
                    'x': 0.01,
                    'xanchor': 'left',
                    'font': {'family': self.title_font_family, 'size': 24, 'color': self.color_text},
                },
                xaxis={'title': 'Centrality', 'showgrid': True, 'gridcolor': 'rgba(148,163,184,0.2)', 'zeroline': False},
                yaxis={'title': 'Density', 'showgrid': True, 'gridcolor': 'rgba(148,163,184,0.2)', 'zeroline': False},
                template='plotly_white',
                plot_bgcolor='#ffffff',
                paper_bgcolor='#ffffff',
                font={'family': 'Arial', 'size': 13, 'color': '#0f172a'},
                margin={'l': 80, 'r': 40, 't': 90, 'b': 70},
            )

            html_path = self.assets_dir / 'figure_thematic_map_2x2.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)

            return generated
        except Exception:
            return []


    def _normalize_keywords(self, raw_keywords):
        if raw_keywords is None:
            return []
        text = str(raw_keywords)
        for sep in [',', '|', '/']:
            text = text.replace(sep, ';')
        tokens = []
        for part in text.split(';'):
            t = ' '.join(part.strip().lower().split())
            if len(t) < 2:
                continue
            if t in {'none', 'na', 'n/a'}:
                continue
            tokens.append(t)
        return tokens

    def _generate_geographic_choropleth(self):
        papers = self.review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED).order_by('id')
        country_counts = Counter()

        for p in papers:
            ext = p.full_text_extraction if isinstance(p.full_text_extraction, dict) else {}
            raw_country = str(ext.get('country') or '').strip()
            if not raw_country:
                continue
            iso3 = self._country_to_iso3(raw_country)
            if not iso3:
                continue
            country_counts[iso3] += 1

        if not country_counts:
            return []

        rows = []
        for iso3, count in sorted(country_counts.items(), key=lambda x: x[1], reverse=True):
            name = self._iso3_to_name(iso3)
            rows.append({'iso3': iso3, 'country': name, 'count': count})

        out_json = self.assets_dir / 'figure_geographic_choropleth.json'
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.express as px

            fig = px.choropleth(
                rows,
                locations='iso3',
                color='count',
                hover_name='country',
                color_continuous_scale='YlGnBu',
                projection='natural earth',
                title='Geographic Distribution of Included Studies',
            )
            fig.update_layout(
                title={
                    'x': 0.01,
                    'xanchor': 'left',
                    'font': {'family': self.title_font_family, 'size': 24, 'color': self.color_text},
                },
                margin={'l': 20, 'r': 20, 't': 80, 'b': 10},
                template='plotly_white',
                paper_bgcolor='#ffffff',
                font={'family': 'Arial', 'size': 13, 'color': '#0f172a'},
                coloraxis_colorbar={'title': 'Study Count'},
            )
            fig.update_geos(
                showcoastlines=True,
                coastlinecolor='rgba(100,116,139,0.7)',
                showcountries=True,
                countrycolor='rgba(100,116,139,0.55)',
                showland=True,
                landcolor='rgb(247,250,252)',
                fitbounds='locations',
            )

            html_path = self.assets_dir / 'figure_geographic_choropleth.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)

            png_path = self.assets_dir / 'figure_geographic_choropleth.png'
            try:
                fig.write_image(str(png_path), width=2000, height=1100, scale=2)
                generated.append(png_path.name)
            except Exception:
                pass

        except Exception:
            pass

        return generated

    def _country_to_iso3(self, country):
        raw = (country or '').strip()
        if not raw:
            return ''

        aliases = {
            'usa': 'USA',
            'u.s.a.': 'USA',
            'u.s.': 'USA',
            'united states': 'USA',
            'uk': 'GBR',
            'u.k.': 'GBR',
            'england': 'GBR',
            'scotland': 'GBR',
            'wales': 'GBR',
            'north korea': 'PRK',
            'south korea': 'KOR',
            'russia': 'RUS',
            'viet nam': 'VNM',
            'iran': 'IRN',
            'lao pdr': 'LAO',
            'czech republic': 'CZE',
            'taiwan': 'TWN',
        }

        key = raw.lower()
        if key in aliases:
            return aliases[key]

        try:
            c = pycountry.countries.lookup(raw)
            return str(getattr(c, 'alpha_3', '') or '')
        except Exception:
            pass

        # Try split for patterns like "United States; Canada"
        for sep in [';', ',', '/', '|']:
            if sep in raw:
                first = raw.split(sep)[0].strip()
                if first and first != raw:
                    return self._country_to_iso3(first)

        return ''

    def _iso3_to_name(self, iso3):
        try:
            c = pycountry.countries.get(alpha_3=iso3)
            if c:
                return c.name
        except Exception:
            pass
        return iso3

    def _generate_temporal_trend(self):
        rows = list(
            self.review.papers.exclude(publication_year__isnull=True)
            .values_list('publication_year', flat=True)
        )
        counts = Counter(int(y) for y in rows if y)
        if not counts:
            return []

        years = sorted(counts.keys())
        values = [counts[y] for y in years]

        out_json = self.assets_dir / 'figure_temporal_trend.json'
        out_json.write_text(
            json.dumps({'year': years, 'count': values}, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        generated = [str(out_json.name)]

        try:
            import plotly.graph_objects as go

            max_y = max(values) if values else 1
            avg_y = round(sum(values) / len(values), 2) if values else 0

            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=years,
                    y=values,
                    marker={'color': self.color_primary},
                    opacity=0.30,
                    name='Publications',
                    hovertemplate='Year %{x}<br>Count %{y}<extra></extra>',
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=years,
                    y=values,
                    mode='lines+markers',
                    line={'color': '#0b6e4f', 'width': 3.5},
                    marker={'size': 8, 'color': '#0b6e4f', 'line': {'color': '#ffffff', 'width': 1}},
                    fill='tozeroy',
                    fillcolor='rgba(11,110,79,0.12)',
                    name='Trend',
                    hovertemplate='Year %{x}<br>Count %{y}<extra></extra>',
                )
            )

            fig.add_hline(
                y=avg_y,
                line={'color': '#6b7280', 'width': 1.5, 'dash': 'dash'},
                annotation_text=f'Mean={avg_y}',
                annotation_position='top left',
                annotation_font={'size': 12, 'color': '#374151'},
            )

            fig.add_annotation(
                x=years[-1],
                y=values[-1],
                text=f'Latest: {values[-1]}',
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=1.2,
                arrowcolor=self.color_secondary,
                ax=-60,
                ay=-35,
                bgcolor='rgba(255,255,255,0.88)',
                bordercolor='#d1d5db',
                borderwidth=1,
                font={'size': 12, 'color': '#111827'},
            )

            fig.update_layout(
                title={
                    'text': 'Temporal Trend of Publications',
                    'x': 0.01,
                    'xanchor': 'left',
                    'font': {'family': self.title_font_family, 'size': 24, 'color': self.color_text},
                },
                xaxis={
                    'title': {'text': 'Publication Year', 'font': {'size': 16, 'family': 'Times New Roman, Georgia, serif'}},
                    'tickmode': 'array',
                    'tickvals': years,
                    'showgrid': True,
                    'gridcolor': self.color_grid,
                    'linecolor': '#334155',
                    'tickfont': {'size': 12, 'family': 'Arial'},
                },
                yaxis={
                    'title': {'text': 'Number of Publications', 'font': {'size': 16, 'family': 'Times New Roman, Georgia, serif'}},
                    'rangemode': 'tozero',
                    'range': [0, max(max_y * 1.22, max_y + 1)],
                    'showgrid': True,
                    'gridcolor': self.color_grid,
                    'linecolor': '#334155',
                    'tickfont': {'size': 12, 'family': 'Arial'},
                },
                template='plotly_white',
                font={'family': 'Arial', 'size': 13, 'color': '#0f172a'},
                plot_bgcolor='#ffffff',
                paper_bgcolor='#ffffff',
                margin={'l': 90, 'r': 40, 't': 90, 'b': 80},
                hovermode='x unified',
                showlegend=False,
            )

            html_path = self.assets_dir / 'figure_temporal_trend.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)

            png_path = self.assets_dir / 'figure_temporal_trend.png'
            svg_path = self.assets_dir / 'figure_temporal_trend.svg'
            pdf_path = self.assets_dir / 'figure_temporal_trend.pdf'
            for out_path, width, height, scale in [
                (png_path, 2200, 1300, 2),
                (svg_path, 2200, 1300, 1),
                (pdf_path, 2200, 1300, 1),
            ]:
                try:
                    fig.write_image(str(out_path), width=width, height=height, scale=scale)
                    generated.append(out_path.name)
                except Exception:
                    continue

        except Exception:
            pass

        return generated

    def _generate_keyword_top_terms_bar(self):
        papers = list(self.review.papers.exclude(keywords='').values_list('keywords', flat=True))
        keyword_counter = Counter()
        for raw in papers:
            for kw in self._normalize_keywords(raw):
                keyword_counter[kw] += 1

        top = keyword_counter.most_common(20)
        if not top:
            return []

        rows = [{'keyword': k, 'count': c} for k, c in top]
        out_json = self.assets_dir / 'figure_keyword_top_terms_bar.json'
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            keywords = [x['keyword'] for x in rows][::-1]
            counts = [x['count'] for x in rows][::-1]
            fig = go.Figure(
                data=[
                    go.Bar(
                        x=counts,
                        y=keywords,
                        orientation='h',
                        marker={'color': self.color_primary},
                        hovertemplate='%{y}<br>Count %{x}<extra></extra>',
                    )
                ]
            )
            fig.update_layout(
                title={'text': 'Top Keyword Frequencies', 'x': 0.01, 'xanchor': 'left', 'font': {'family': 'Times New Roman, Georgia, serif', 'size': 24}},
                xaxis_title='Frequency',
                yaxis_title='Keyword',
                template='plotly_white',
                height=900,
                margin={'l': 220, 'r': 40, 't': 80, 'b': 60},
                font={'family': 'Arial', 'size': 13},
            )
            html_path = self.assets_dir / 'figure_keyword_top_terms_bar.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated

    def _generate_journal_impact(self):
        rows = list(self.review.papers.values_list('journal', flat=True))
        cleaned = [str(j).strip() for j in rows if str(j).strip()]
        counts = Counter(cleaned)
        top = counts.most_common(10)
        if not top:
            return []

        data = [{'journal': j, 'count': c} for j, c in top]
        out_json = self.assets_dir / 'table_journal_impact_top10.json'
        out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            fig = go.Figure(
                data=[
                    go.Table(
                        header=self._table_header(['Journal', 'Count']),
                        cells=self._table_cells([[d['journal'] for d in data], [d['count'] for d in data]], height=28),
                    )
                ]
            )
            self._apply_figure_layout(fig, 'Top 10 Journals by Frequency', height=500, margin={'l': 30, 'r': 30, 't': 70, 'b': 20})
            html_path = self.assets_dir / 'table_journal_impact_top10.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated

    def _generate_study_characteristics_table(self):
        papers = self.review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED).order_by('id')
        rows = []
        for p in papers:
            ext = p.full_text_extraction if isinstance(p.full_text_extraction, dict) else {}
            qual = p.full_text_quality if isinstance(p.full_text_quality, dict) else {}
            key_findings = ext.get('key_findings')
            if isinstance(key_findings, dict):
                kf = str(key_findings.get('summary') or '').strip()
            else:
                kf = str(key_findings or '').strip()
            rows.append(
                {
                    'paper_id': p.id,
                    'author_year': str(ext.get('author_year') or '').strip(),
                    'title': p.title,
                    'population': str(ext.get('population') or '').strip(),
                    'study_design': str(ext.get('study_design_canonical') or ext.get('study_design') or '').strip(),
                    'country': str(ext.get('country') or '').strip(),
                    'key_finding': kf,
                    'quality_score': qual.get('total_score'),
                }
            )

        out_json = self.assets_dir / 'table_study_characteristics.json'
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            max_rows = 40
            limited = rows[:max_rows]
            fig = go.Figure(
                data=[
                    go.Table(
                        header=self._table_header(['ID', 'Author-Year', 'Country', 'Design', 'Population', 'Key Finding', 'Quality']),
                        cells=self._table_cells([
                            [r['paper_id'] for r in limited],
                            [r['author_year'] for r in limited],
                            [r['country'] for r in limited],
                            [r['study_design'] for r in limited],
                            [self._truncate(r['population'], 70) for r in limited],
                            [self._truncate(r['key_finding'], 120) for r in limited],
                            [r['quality_score'] for r in limited],
                        ], height=26),
                    )
                ]
            )
            self._apply_figure_layout(
                fig,
                f'Study Characteristics Table (showing {len(limited)} of {len(rows)})',
                height=950,
                margin={'l': 20, 'r': 20, 't': 80, 'b': 20},
            )
            html_path = self.assets_dir / 'table_study_characteristics.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated

    def _generate_quality_assessment_table(self):
        papers = self.review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED).order_by('id')
        rows = []
        for p in papers:
            q = p.full_text_quality if isinstance(p.full_text_quality, dict) else {}
            rows.append(
                {
                    'paper_id': p.id,
                    'title': p.title,
                    'dim_objectives': q.get('dim_objectives'),
                    'dim_design': q.get('dim_design'),
                    'dim_data': q.get('dim_data'),
                    'dim_analysis': q.get('dim_analysis'),
                    'dim_bias': q.get('dim_bias'),
                    'total_score': q.get('total_score'),
                    'risk_of_bias': q.get('risk_of_bias'),
                }
            )

        out_json = self.assets_dir / 'table_quality_assessment.json'
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            fig = go.Figure(
                data=[
                    go.Table(
                        header=self._table_header(['Paper ID', 'Objectives', 'Design', 'Data', 'Analysis', 'Bias', 'Total Score', 'Risk of Bias']),
                        cells=self._table_cells([
                            [r['paper_id'] for r in rows],
                            [r['dim_objectives'] for r in rows],
                            [r['dim_design'] for r in rows],
                            [r['dim_data'] for r in rows],
                            [r['dim_analysis'] for r in rows],
                            [r['dim_bias'] for r in rows],
                            [r['total_score'] for r in rows],
                            [r['risk_of_bias'] for r in rows],
                        ], height=24),
                    )
                ]
            )
            self._apply_figure_layout(fig, 'Quality Assessment Table', height=900, margin={'l': 20, 'r': 20, 't': 80, 'b': 20})
            html_path = self.assets_dir / 'table_quality_assessment.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated

    def _generate_scopus_query_strings_table(self):
        queries = list(self.review.search_queries.all().order_by('id'))
        if not queries:
            return []

        rows = []
        for q in queries:
            rows.append(
                {
                    'focus': q.get_focus_display() if hasattr(q, 'get_focus_display') else str(q.focus),
                    'query_string': q.query_string,
                    'rationale': q.rationale,
                    'is_executed': bool(q.is_executed),
                }
            )

        out_json = self.assets_dir / 'table_scopus_query_strings.json'
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            fig = go.Figure(
                data=[
                    go.Table(
                        header=self._table_header(['Focus', 'Query String', 'Rationale', 'Executed']),
                        cells=self._table_cells([
                            [r['focus'] for r in rows],
                            [self._truncate(r['query_string'], 360) for r in rows],
                            [self._truncate(r['rationale'], 180) for r in rows],
                            ['Yes' if r['is_executed'] else 'No' for r in rows],
                        ], height=30),
                    )
                ]
            )
            self._apply_figure_layout(fig, 'Scopus Query Strings', height=820, margin={'l': 20, 'r': 20, 't': 80, 'b': 20})
            html_path = self.assets_dir / 'table_scopus_query_strings.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated

    def _generate_tccm_analysis_table(self):
        scaffold = self.review.scaffold_data if isinstance(self.review.scaffold_data, dict) else {}
        tccm = scaffold.get('tccm_summary', {}) if isinstance(scaffold.get('tccm_summary', {}), dict) else {}
        if not tccm:
            return []

        theory = tccm.get('theory_dimension', {}) if isinstance(tccm.get('theory_dimension', {}), dict) else {}
        chars = tccm.get('characteristics_dimension', {}) if isinstance(tccm.get('characteristics_dimension', {}), dict) else {}
        context = tccm.get('context_dimension', {}) if isinstance(tccm.get('context_dimension', {}), dict) else {}
        methods = tccm.get('methods_dimension', {}) if isinstance(tccm.get('methods_dimension', {}), dict) else {}

        theory_dominant = theory.get('dominant_theory') or theory.get('dominant_theories', [])
        theory_present = theory.get('theories_used') or theory.get('theories_present', {})
        chars_dominant = chars.get('unit_of_analysis', {}).get('dominant') if isinstance(chars.get('unit_of_analysis', {}), dict) else chars.get('design_distribution', {})
        chars_present = {
            'sample_types': chars.get('sample_types', {}),
            'sample_size_distribution': chars.get('sample_size_distribution', {}),
            'journal_field_distribution': chars.get('journal_field_distribution', {}),
        }
        chars_absent = chars.get('unit_of_analysis', {}).get('absent', []) if isinstance(chars.get('unit_of_analysis', {}), dict) else []
        context_dominant = context.get('geographic_distribution', [])[:3] if isinstance(context.get('geographic_distribution', []), list) else context.get('country_distribution', {})
        context_present = {
            'economic_context_distribution': context.get('economic_context_distribution', {}),
            'platform_type_distribution': context.get('platform_type_distribution', {}),
            'population_group_distribution': context.get('population_group_distribution', {}),
        }
        methods_dominant = methods.get('paradigm_distribution', {})
        methods_present = {
            'data_collection_distribution': methods.get('data_collection_distribution', {}),
            'analysis_distribution': methods.get('analysis_distribution', {}),
            'pre_registered_pct': methods.get('pre_registered_pct'),
            'multi_sample_replication_pct': methods.get('multi_sample_replication_pct'),
        }

        rows = [
            {
                'dimension': 'Theory',
                'findings_and_gaps': self._build_tccm_dimension_text(
                    dominant=theory_dominant,
                    present=theory_present,
                    absent=theory.get('absent_theories', []),
                    narrative=theory.get('theory_narrative', ''),
                ),
            },
            {
                'dimension': 'Characteristics',
                'findings_and_gaps': self._build_tccm_dimension_text(
                    dominant=chars_dominant,
                    present=chars_present,
                    absent=chars_absent,
                    narrative=chars.get('characteristics_narrative', ''),
                ),
            },
            {
                'dimension': 'Context',
                'findings_and_gaps': self._build_tccm_dimension_text(
                    dominant=context_dominant,
                    present=context_present,
                    absent=(context.get('underrepresented_regions', []) or []) + (context.get('underrepresented_populations', []) or []),
                    narrative=context.get('context_narrative', ''),
                ),
            },
            {
                'dimension': 'Methods',
                'findings_and_gaps': self._build_tccm_dimension_text(
                    dominant=methods_dominant,
                    present=methods_present,
                    absent=methods.get('absent_methods', []),
                    narrative=methods.get('methods_narrative', ''),
                ),
            },
        ]

        out_json = self.assets_dir / 'table_tccm_analysis.json'
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            fig = go.Figure(
                data=[
                    go.Table(
                        header=self._table_header(['Dimension', 'Findings and Gaps']),
                        cells=self._table_cells(
                            [
                                [r['dimension'] for r in rows],
                                [self._truncate(r['findings_and_gaps'], 1000) for r in rows],
                            ],
                            height=55,
                        ),
                    )
                ]
            )
            self._apply_figure_layout(fig, 'TCCM Analysis Table', height=900, margin={'l': 20, 'r': 20, 't': 80, 'b': 20})
            html_path = self.assets_dir / 'table_tccm_analysis.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated

    def _build_tccm_dimension_text(self, dominant, present, absent, narrative):
        parts = []
        dominant_text = self._format_tccm_value(dominant)
        present_text = self._format_tccm_value(present)
        absent_text = self._format_tccm_value(absent)
        if dominant_text:
            parts.append(f'Dominant: {dominant_text}')
        if present_text:
            parts.append(f'Present: {present_text}')
        if absent_text:
            parts.append(f'Absent/Gaps: {absent_text}')
        n = str(narrative or '').strip()
        if n:
            parts.append(f'Narrative: {n}')
        return ' | '.join(parts)

    def _format_tccm_value(self, value):
        if isinstance(value, dict):
            chunks = []
            for key, val in value.items():
                chunks.append(f'{key}: {val}')
            return '; '.join(chunks)
        if isinstance(value, list):
            return '; '.join(str(x) for x in value if str(x).strip())
        return str(value or '').strip()

    def _generate_pico_and_criteria_table(self):
        rows = [
            {'component': 'Population', 'content': self.review.pico_population or ''},
            {'component': 'Intervention', 'content': self.review.pico_intervention or ''},
            {'component': 'Comparison', 'content': self.review.pico_comparison or ''},
            {'component': 'Outcomes', 'content': self.review.pico_outcomes or ''},
            {'component': 'Inclusion Criteria', 'content': self.review.inclusion_criteria or ''},
            {'component': 'Exclusion Criteria', 'content': self.review.exclusion_criteria or ''},
        ]

        out_json = self.assets_dir / 'table_pico_and_criteria.json'
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            fig = go.Figure(
                data=[
                    go.Table(
                        header=self._table_header(['Component', 'Content']),
                        cells=self._table_cells([
                            [r['component'] for r in rows],
                            [self._truncate(r['content'], 520) for r in rows],
                        ], height=34),
                    )
                ]
            )
            self._apply_figure_layout(fig, 'PICO and Criteria', height=760, margin={'l': 20, 'r': 20, 't': 80, 'b': 20})
            html_path = self.assets_dir / 'table_pico_and_criteria.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated
    def _generate_thematic_crosstab(self):
        rows = []
        for theme in self.review.theme_syntheses.all().order_by('order_index', 'id'):
            for p in theme.papers.all().order_by('id'):
                ext = p.full_text_extraction if isinstance(p.full_text_extraction, dict) else {}
                short_ref = str(ext.get('author_year') or '').strip() or p.title[:80]
                rows.append(
                    {
                        'theme_name': theme.theme_name_locked,
                        'evidence_grade': theme.evidence_grade,
                        'paper_id': p.id,
                        'short_ref': short_ref,
                    }
                )

        out_json = self.assets_dir / 'table_thematic_crosstab.json'
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            fig = go.Figure(
                data=[
                    go.Table(
                        header=self._table_header(['Theme', 'Evidence Grade', 'Paper ID', 'Short Ref']),
                        cells=self._table_cells([
                            [r['theme_name'] for r in rows],
                            [r['evidence_grade'] for r in rows],
                            [r['paper_id'] for r in rows],
                            [r['short_ref'] for r in rows],
                        ], height=24),
                    )
                ]
            )
            self._apply_figure_layout(fig, 'Thematic Cross-Tabulation', height=1000, margin={'l': 20, 'r': 20, 't': 80, 'b': 20})
            html_path = self.assets_dir / 'table_thematic_crosstab.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated
    def _generate_evidence_strength_heatmap(self):
        themes = list(self.review.theme_syntheses.all().order_by('order_index', 'id'))
        if not themes:
            return []

        bands = ['low', 'moderate', 'high']
        matrix = []
        labels = []
        for theme in themes:
            counts = defaultdict(int)
            for p in theme.papers.all():
                q = p.full_text_quality if isinstance(p.full_text_quality, dict) else {}
                rob = str(q.get('risk_of_bias') or '').strip().lower()
                if rob in bands:
                    counts[rob] += 1
            matrix.append([counts['low'], counts['moderate'], counts['high']])
            labels.append(theme.theme_name_locked)

        out_json = self.assets_dir / 'figure_evidence_strength_heatmap.json'
        out_json.write_text(
            json.dumps({'themes': labels, 'bands': bands, 'matrix': matrix}, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            fig = go.Figure(
                data=go.Heatmap(
                    z=matrix,
                    x=['Low Risk', 'Moderate Risk', 'High Risk'],
                    y=labels,
                    colorscale='YlGnBu',
                    colorbar={'title': 'Paper Count'},
                )
            )
            fig.update_layout(
                title='Evidence Strength Heatmap (Theme x Quality Risk)',
                template='plotly_white',
                font={'family': 'Arial', 'size': 13},
            )
            html_path = self.assets_dir / 'figure_evidence_strength_heatmap.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated

    def _generate_prisma_payload(self):
        scaffold = self.review.scaffold_data if isinstance(self.review.scaffold_data, dict) else {}
        prisma = scaffold.get('prisma_counts', {}) if isinstance(scaffold.get('prisma_counts', {}), dict) else {}
        out_json = self.assets_dir / 'figure_prisma_counts.json'
        out_json.write_text(json.dumps(prisma, ensure_ascii=False, indent=2), encoding='utf-8')
        return [out_json.name]

    def _generate_prisma_flow_diagram(self):
        scaffold = self.review.scaffold_data if isinstance(self.review.scaffold_data, dict) else {}
        prisma = scaffold.get('prisma_counts', {}) if isinstance(scaffold.get('prisma_counts', {}), dict) else {}

        scopus_retrieved = int(prisma.get('scopus_retrieved') or 0)
        after_dedup = int(prisma.get('after_dedup') or 0)
        passed_ta = int(prisma.get('passed_ta') or 0)
        pdfs_retrieved = int(prisma.get('pdfs_retrieved') or 0)
        passed_fulltext = int(prisma.get('passed_fulltext') or 0)
        final_included = int(prisma.get('final_included') or 0)

        payload = {
            'nodes': [
                {'id': 0, 'label': f'Records Identified\n{scopus_retrieved}'},
                {'id': 1, 'label': f'After Deduplication\n{after_dedup}'},
                {'id': 2, 'label': f'Passed Title/Abstract\n{passed_ta}'},
                {'id': 3, 'label': f'PDFs Retrieved\n{pdfs_retrieved}'},
                {'id': 4, 'label': f'Passed Full-Text\n{passed_fulltext}'},
                {'id': 5, 'label': f'Final Included\n{final_included}'},
            ],
            'links': [
                {'source': 0, 'target': 1, 'value': max(min(scopus_retrieved, after_dedup), 0)},
                {'source': 1, 'target': 2, 'value': max(min(after_dedup, passed_ta), 0)},
                {'source': 2, 'target': 3, 'value': max(min(passed_ta, pdfs_retrieved), 0)},
                {'source': 3, 'target': 4, 'value': max(min(pdfs_retrieved, passed_fulltext), 0)},
                {'source': 4, 'target': 5, 'value': max(min(passed_fulltext, final_included), 0)},
            ],
        }

        out_json = self.assets_dir / 'figure_prisma_flow_diagram.json'
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        generated = [out_json.name]

        try:
            import plotly.graph_objects as go
            fig = go.Figure(
                data=[
                    go.Sankey(
                        node={
                            'pad': 22,
                            'thickness': 22,
                            'line': {'color': '#475569', 'width': 0.8},
                            'label': [n['label'] for n in payload['nodes']],
                            'color': ['#1f4e79', '#2563eb', '#0ea5e9', '#0f766e', '#16a34a', '#15803d'],
                        },
                        link={
                            'source': [l['source'] for l in payload['links']],
                            'target': [l['target'] for l in payload['links']],
                            'value': [l['value'] for l in payload['links']],
                            'color': ['rgba(37,99,235,0.28)'] * len(payload['links']),
                        },
                    )
                ]
            )
            fig.update_layout(
                title='PRISMA 2020 Flow Diagram',
                template='plotly_white',
                font={'family': 'Arial', 'size': 12},
                margin={'l': 30, 'r': 30, 't': 60, 'b': 20},
                height=620,
            )
            html_path = self.assets_dir / 'figure_prisma_flow_diagram.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass

        return generated

    def _generate_cleaning_summary(self):
        sp = self.review.stage_progress if isinstance(self.review.stage_progress, dict) else {}
        phase5 = sp.get('phase_5_report', {}) if isinstance(sp.get('phase_5_report', {}), dict) else {}
        ingest_quality = phase5.get('ingest_quality', {}) if isinstance(phase5.get('ingest_quality', {}), dict) else {}
        before = int(ingest_quality.get('total_papers_imported') or 0)
        dupes = int(ingest_quality.get('duplicates_removed') or 0)
        after = max(before - dupes, 0)
        payload = {'before_import': before, 'duplicates_removed': dupes, 'after_dedupe': after}

        out_json = self.assets_dir / 'figure_cleaning_summary.json'
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

        generated = [out_json.name]
        try:
            import plotly.graph_objects as go
            x = ['Imported', 'Duplicates Removed', 'After Dedupe']
            y = [before, dupes, after]
            fig = go.Figure(data=[go.Bar(x=x, y=y, marker_color=['#1f4e79', '#b91c1c', '#0f766e'])])
            fig.update_layout(title='Cleaning Summary (Before vs After Deduplication)', template='plotly_white')
            html_path = self.assets_dir / 'figure_cleaning_summary.html'
            fig.write_html(str(html_path), include_plotlyjs='cdn', full_html=True)
            generated.append(html_path.name)
        except Exception:
            pass
        return generated

    def _truncate(self, text, max_len):
        val = str(text or '').strip()
        if len(val) <= max_len:
            return val
        return val[: max_len - 1].rstrip() + '?'

    def _persist_stage(self, generated, bundle):
        self.review.refresh_from_db(fields=['stage_progress'])
        stage_progress = self.review.stage_progress if isinstance(self.review.stage_progress, dict) else {}
        stage = stage_progress.get(self.stage_key, {}) if isinstance(stage_progress.get(self.stage_key, {}), dict) else {}
        logs = list(stage.get('logs') or [])
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': 'generated',
                'bundle': bundle,
                'count': len(generated),
                'files': generated,
            },
        )
        stage.update(
            {
                'status': 'done',
                'last_bundle': bundle,
                'last_generated_count': len(generated),
                'last_generated_at': timezone.now().isoformat(),
                'logs': logs[:200],
            }
        )
        stage_progress[self.stage_key] = stage
        self.review.stage_progress = stage_progress
        self.review.save(update_fields=['stage_progress'])


def generate_visual_assets(review_id, bundle='all'):
    return VisualAssetsService(review_id=review_id).generate(bundle=bundle)






