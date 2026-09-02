Mini bar chart + axis. Muted bars for history/baseline, green for the period being talked about, ink in the rail.

```jsx
<Bars values={[780,640,1110,930,690,210,250]} max={1180} size="sm" />
<Bars values={[910,1180,760,1020,840,330,244]} max={1180} size="sm" tone="in" />
<Axis labels={["8am","1pm","6pm"]} />
```