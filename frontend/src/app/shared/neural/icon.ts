import {
  booleanAttribute,
  Component,
  computed,
  input,
  makeEnvironmentProviders,
  type EnvironmentProviders,
} from '@angular/core';
import {
  LucideAlertCircle,
  LucideAlertTriangle,
  LucideArrowUpDown,
  LucideBox,
  LucideCheck,
  LucideChevronDown,
  LucideChevronLeft,
  LucideChevronRight,
  LucideCircleCheck,
  LucideCircleQuestionMark,
  LucideCircleX,
  LucideClock,
  LucideColumns2,
  LucideCopy,
  LucideCpu,
  LucideDownload,
  LucideDynamicIcon,
  LucideEye,
  LucideFileVideo,
  LucideFilm,
  LucideFlaskConical,
  LucideFolder,
  LucideFolderOpen,
  LucideHome,
  LucideImage,
  LucideLayoutGrid,
  LucideLoaderCircle,
  LucideMoreHorizontal,
  LucidePauseCircle,
  LucidePencil,
  LucidePlay,
  LucidePlugZap,
  LucidePlus,
  LucideRadio,
  LucideRefreshCw,
  LucideRotateCcw,
  LucideSearch,
  LucideSettings,
  LucideSparkles,
  LucideTrash2,
  LucideUpload,
  LucideWandSparkles,
  provideLucideIcons,
} from '@lucide/angular';

export type NIconName = string;
export type NIconSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

const iconSize: Record<NIconSize, string> = {
  xs: '14px',
  sm: '18px',
  md: '22px',
  lg: '28px',
  xl: '42px',
};

const icons = [
  LucideAlertCircle,
  LucideAlertTriangle,
  LucideArrowUpDown,
  LucideBox,
  LucideCheck,
  LucideChevronDown,
  LucideChevronLeft,
  LucideChevronRight,
  LucideCircleCheck,
  LucideCircleQuestionMark,
  LucideCircleX,
  LucideClock,
  LucideColumns2,
  LucideCopy,
  LucideCpu,
  LucideDownload,
  LucideEye,
  LucideFileVideo,
  LucideFilm,
  LucideFlaskConical,
  LucideFolder,
  LucideFolderOpen,
  LucideHome,
  LucideImage,
  LucideLayoutGrid,
  LucideLoaderCircle,
  LucideMoreHorizontal,
  LucidePauseCircle,
  LucidePencil,
  LucidePlay,
  LucidePlugZap,
  LucidePlus,
  LucideRadio,
  LucideRefreshCw,
  LucideRotateCcw,
  LucideSearch,
  LucideSettings,
  LucideSparkles,
  LucideTrash2,
  LucideUpload,
  LucideWandSparkles,
] as const;

const fallbackIcon = 'circle-question-mark';

// Nombres (y alias) registrados: un nombre desconocido haría lanzar a Lucide y romper el render.
const registeredIconNames = new Set<string>(
  icons.flatMap((icon) => [icon.icon.name, ...(icon.icon.aliases ?? [])]),
);

export function provideNeuralIcons(): EnvironmentProviders {
  return makeEnvironmentProviders([provideLucideIcons(...icons)]);
}

@Component({
  selector: 'n-icon',
  standalone: true,
  imports: [LucideDynamicIcon],
  host: {
    '[style.width]': 'dimension()',
    '[style.height]': 'dimension()',
    '[attr.data-icon-name]': 'name()',
  },
  template: `
    @if (name()) {
      <svg
        class="n-icon"
        [lucideIcon]="resolvedName()"
        [attr.aria-hidden]="decorative() ? 'true' : null"
        [attr.aria-label]="decorative() ? null : label()"
      />
    }
  `,
  styles: [
    `
      :host {
        display: inline-flex;
        flex: 0 0 auto;
        align-items: center;
        justify-content: center;
        min-width: var(--n-icon-current-size, 18px);
        color: currentColor;
        line-height: 0;
        vertical-align: -0.15em;
      }

      .n-icon {
        display: block;
        width: 100%;
        height: 100%;
        stroke: currentColor;
      }
    `,
  ],
})
export class NIcon {
  readonly name = input<NIconName | ''>('');
  readonly size = input<NIconSize>('md');
  readonly label = input<string | null>(null);
  readonly decorative = input(true, { transform: booleanAttribute });

  readonly resolvedName = computed(() => {
    const name = this.name();
    return registeredIconNames.has(name) ? name : fallbackIcon;
  });

  readonly dimension = computed(() => iconSize[this.size()] ?? iconSize.md);
}
