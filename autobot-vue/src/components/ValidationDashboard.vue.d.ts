// Issue #156 Fix: TypeScript declaration for ${file}.vue
import { DefineComponent } from 'vue'
declare const component: DefineComponent<{}, {}, any>
export default component
