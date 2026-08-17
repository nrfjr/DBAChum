import { use } from 'echarts/core'

import {
  LineChart,
} from 'echarts/charts'

import {
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
} from 'echarts/components'

import {
  CanvasRenderer,
} from 'echarts/renderers'


use([
  LineChart,

  DataZoomComponent,
  GridComponent,
  TooltipComponent,

  CanvasRenderer,
])