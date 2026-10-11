import { Component, computed, input, model, output } from '@angular/core';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NImageCompare } from '@neuralangular/angular-ui/image-compare';

import { translate } from '../../core/i18n/i18n';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { PreviewFrameVm, WorkspaceVm } from '../../core/models/oroya.models';

export type PreviewCompareMode = 'slider' | 'side_by_side';
export type PreviewZoom = 'fit' | '100%';

@Component({
  selector: 'ov-video-preview',
  standalone: true,
  imports: [NButton, NIcon, NImageCompare, TranslatePipe],
  template: `
    <section class="ov-video-preview">
      <div class="ov-video-preview__toolbar">
        <div class="ov-video-preview__modes">
          <button
            type="button"
            [class.on]="compareMode() === 'slider'"
            (click)="setCompareMode('slider')"
          >
            <n-icon name="columns-2" size="sm" />
            {{ 'preview.wipe' | t }}
          </button>
          <button
            type="button"
            [class.on]="compareMode() === 'side_by_side'"
            (click)="setCompareMode('side_by_side')"
          >
            <n-icon name="layout-grid" size="sm" />
            {{ 'preview.sideBySide' | t }}
          </button>
        </div>
        @if (filtersActive()) {
          <span class="ov-video-preview__filters-badge" [title]="'preview.filtersHint' | t">
            <n-icon name="sparkles" size="sm" />
            {{ 'preview.filtersApplied' | t }}
          </span>
        }
        <div class="ov-video-preview__modes">
          <button type="button" [class.on]="zoom() === 'fit'" (click)="setZoom('fit')">{{ 'preview.fit' | t }}</button>
          <button type="button" [class.on]="zoom() === '100%'" (click)="setZoom('100%')">100%</button>
        </div>
      </div>
      <div
        class="ov-video-preview__stage"
        [class.ov-video-preview__stage--zoomed]="zoom() === '100%'"
      >
        @if (!beforeSrc() && !afterSrc()) {
          <div class="ov-video-preview__empty">
            <n-icon name="film" size="xl" />
            <strong>{{ 'preview.emptyTitle' | t }}</strong>
            <span>{{ 'preview.emptyBody' | t }}</span>
          </div>
        } @else if (!afterSrc()) {
          <figure class="ov-video-preview__original-only">
            <figcaption>{{ beforeLabel() }}</figcaption>
            <img [src]="beforeSrc()" [alt]="'preview.originalAlt' | t" />
            <span class="ov-video-preview__hint">
              <n-icon name="sparkles" size="sm" />
              {{ 'preview.originalOnlyHint' | t }}
            </span>
          </figure>
        } @else if (compareMode() === 'slider') {
          <n-image-compare
            [beforeSrc]="beforeSrc()"
            [afterSrc]="afterSrc()"
            [beforeLabel]="beforeLabel()"
            [afterLabel]="afterLabel()"
            [beforeAlt]="'preview.originalAlt' | t"
            [afterAlt]="'preview.enhancedAlt' | t"
            [value]="compareValue()"
            (valueChange)="compareValue.set($event)"
          />
        } @else {
          <div class="ov-video-preview__split">
            <figure>
              <figcaption>{{ beforeLabel() }}</figcaption>
              <div class="ov-video-preview__pane" #beforePane (scroll)="syncScroll(beforePane, afterPane)">
                <img [src]="beforeSrc()" [alt]="'preview.originalAlt' | t" [class.natural]="zoom() === '100%'" />
              </div>
            </figure>
            <figure>
              <figcaption>{{ afterLabel() }}</figcaption>
              <div class="ov-video-preview__pane" #afterPane (scroll)="syncScroll(afterPane, beforePane)">
                <img [src]="afterSrc()" [alt]="'preview.enhancedAlt' | t" [class.natural]="zoom() === '100%'" />
              </div>
            </figure>
          </div>
        }
      </div>
      <footer>
        <div class="ov-video-preview__time">
          <span>{{ timecode() }}</span>
          <small>/ {{ workspace().project.duration }}</small>
          @if (frameLabel()) {
            <small>{{ frameLabel() }}</small>
          }
        </div>
        <div class="ov-video-preview__frames">
          @if (frames().length) {
            @for (frame of frames(); track frame.index) {
              <button
                type="button"
                class="ov-video-preview__frame"
                [class.ov-video-preview__frame--selected]="frame.index === selectedFrameIndex()"
                (click)="frameSelected.emit(frame.index)"
                [attr.aria-label]="'preview.frameAria' | t: { index: frame.index }"
              >
                @if (frame.enhancedUrl || frame.originalUrl) {
                  <img [src]="frame.enhancedUrl || frame.originalUrl" alt="" />
                }
              </button>
            }
          } @else {
            @for (frame of workspace().timelineFrames; track $index) {
              <span [class]="'ov-video-preview__frame ov-video-preview__frame--' + frame"></span>
            }
          }
        </div>
        <div class="ov-video-preview__tools">
          <n-button
            variant="secondary"
            size="sm"
            iconOnly
            [ariaLabel]="'preview.openFrame' | t"
            [disabled]="!snapshotAvailable()"
            (click)="snapshotRequested.emit()"
          >
            <n-icon name="image" size="sm" />
          </n-button>
          <n-button
            variant="secondary"
            size="sm"
            iconOnly
            [ariaLabel]="'preview.focus' | t"
            [disabled]="!snapshotAvailable()"
            (click)="focusRequested.emit()"
          >
            <n-icon name="eye" size="sm" />
          </n-button>
        </div>
      </footer>
    </section>
  `,
  styles: [
    `
      :host {
        display: block;
        min-width: 0;
      }

      .ov-video-preview {
        display: grid;
        grid-template-rows: auto minmax(320px, 1fr) auto;
        min-height: 0;
      }

      .ov-video-preview__toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 10px 18px;
        border-bottom: 1px solid var(--n-border-1);
        background: rgba(255, 255, 255, 0.02);
      }

      .ov-video-preview__modes {
        display: inline-flex;
        overflow: hidden;
        border: 1px solid var(--n-border-1);
        border-radius: 999px;
      }

      .ov-video-preview__modes button {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 5px 14px;
        border: 0;
        background: transparent;
        color: var(--n-text-3);
        font-size: 0.74rem;
        font-weight: 700;
        cursor: pointer;
      }

      .ov-video-preview__modes button.on {
        background: color-mix(in srgb, var(--n-color-primary), transparent 82%);
        color: var(--n-text-1);
      }

      .ov-video-preview__filters-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border: 1px solid color-mix(in srgb, var(--n-color-primary), transparent 60%);
        border-radius: 999px;
        color: var(--n-color-primary);
        font-size: 0.72rem;
        font-weight: 700;
      }

      .ov-video-preview__stage {
        display: grid;
        place-items: center;
        min-height: 0;
        padding: clamp(18px, 5vw, 72px);
      }

      .ov-video-preview__stage--zoomed {
        padding: 12px;
      }

      .ov-video-preview__empty {
        display: grid;
        justify-items: center;
        gap: 8px;
        color: var(--n-text-4);
        text-align: center;
      }

      .ov-video-preview__empty strong {
        color: var(--n-text-2);
        font-size: 0.95rem;
      }

      .ov-video-preview__empty span {
        max-width: 320px;
        font-size: 0.78rem;
      }

      .ov-video-preview__stage n-image-compare {
        width: min(100%, 1180px);
      }

      .ov-video-preview__original-only {
        position: relative;
        display: grid;
        gap: 6px;
        width: min(100%, 1180px);
        margin: 0;
      }

      .ov-video-preview__original-only figcaption {
        color: var(--n-text-3);
        font-size: 0.74rem;
        font-weight: 700;
        text-transform: uppercase;
      }

      .ov-video-preview__original-only img {
        width: 100%;
        max-height: 62vh;
        object-fit: contain;
        border-radius: var(--n-radius-md);
        background: #000;
      }

      .ov-video-preview__hint {
        position: absolute;
        bottom: 12px;
        left: 50%;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-full);
        background: color-mix(in srgb, var(--n-bg-canvas), transparent 15%);
        color: var(--n-text-2);
        font-size: 0.78rem;
        transform: translateX(-50%);
        white-space: nowrap;
      }

      .ov-video-preview__split {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        width: min(100%, 1180px);
        min-width: 0;
      }

      .ov-video-preview__split figure {
        display: grid;
        gap: 6px;
        min-width: 0;
        margin: 0;
      }

      .ov-video-preview__split figcaption {
        color: var(--n-text-3);
        font-size: 0.72rem;
        font-weight: 800;
        text-transform: uppercase;
      }

      .ov-video-preview__pane {
        overflow: auto;
        max-height: 62vh;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-md);
        background: #090a16;
      }

      .ov-video-preview__pane img {
        display: block;
        width: 100%;
        height: auto;
      }

      .ov-video-preview__pane img.natural {
        width: auto;
        max-width: none;
      }

      footer {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        align-items: center;
        gap: 20px;
        min-height: 82px;
        padding: 14px 18px;
        border-top: 1px solid var(--n-border-1);
        background: rgba(255, 255, 255, 0.025);
      }

      .ov-video-preview__time {
        display: grid;
        gap: 2px;
        width: 110px;
        color: var(--n-text-3);
        font-family: var(--n-font-mono);
        font-size: 0.75rem;
      }

      .ov-video-preview__time small {
        color: var(--n-text-4);
      }

      .ov-video-preview__frames {
        display: grid;
        grid-template-columns: repeat(10, minmax(36px, 1fr));
        gap: 4px;
        min-width: 0;
        overflow: hidden;
      }

      .ov-video-preview__frame {
        position: relative;
        height: 42px;
        overflow: hidden;
        border: 1px solid var(--n-border-1);
        border-radius: 6px;
        background: #090a16;
        cursor: pointer;
        padding: 0;
      }

      button.ov-video-preview__frame:hover {
        border-color: rgba(138, 180, 248, 0.62);
      }

      .ov-video-preview__frame--selected {
        border-color: var(--n-color-primary);
        box-shadow: 0 0 0 1px color-mix(in srgb, var(--n-color-primary), transparent 20%);
      }

      .ov-video-preview__frame img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .ov-video-preview__frame--violet {
        background: linear-gradient(145deg, #111248, #1a1040);
      }

      .ov-video-preview__frame--blue {
        background: linear-gradient(145deg, #07152e, #111a52);
      }

      .ov-video-preview__frame--green {
        background: linear-gradient(145deg, #08212b, #0a3322);
      }

      .ov-video-preview__frame--rose {
        background: linear-gradient(145deg, #2c0b1d, #4b1230);
      }

      .ov-video-preview__tools {
        display: flex;
        gap: 8px;
      }

      @media (max-width: 900px) {
        footer {
          grid-template-columns: 1fr;
        }

        .ov-video-preview__time {
          width: auto;
        }

        .ov-video-preview__frames {
          grid-template-columns: repeat(5, minmax(36px, 1fr));
        }

        .ov-video-preview__split {
          grid-template-columns: 1fr;
        }
      }
    `,
  ],
})
export class OvVideoPreviewComponent {
  readonly workspace = input.required<WorkspaceVm>();
  readonly beforeSrc = input('');
  readonly afterSrc = input('');
  readonly beforeLabel = input(translate('workspace.original'));
  readonly afterLabel = input(translate('workspace.enhanced'));
  readonly frames = input<PreviewFrameVm[]>([]);
  readonly selectedFrameIndex = input<number | null>(null);
  readonly snapshotAvailable = input(false);
  readonly videoFps = input(30);
  readonly totalFrames = input(0);
  readonly filtersActive = input(false);
  readonly compareMode = model<PreviewCompareMode>('slider');
  readonly zoom = model<PreviewZoom>('fit');
  readonly frameSelected = output<number>();
  readonly snapshotRequested = output<void>();
  readonly focusRequested = output<void>();
  readonly compareValue = model(50);
  readonly comparePercent = computed(() => `${Math.round(this.compareValue())}%`);

  readonly timecode = computed(() => {
    const index = this.selectedFrameIndex();
    const fps = this.videoFps() > 0 ? this.videoFps() : 30;
    if (index === null || index < 0) {
      return '--:--:--';
    }

    const totalSeconds = Math.floor(index / fps);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return [hours, minutes, seconds].map((part) => part.toString().padStart(2, '0')).join(':');
  });

  readonly frameLabel = computed(() => {
    const index = this.selectedFrameIndex();
    if (index === null || index < 0) {
      return '';
    }

    const total = this.totalFrames();
    return total > 0
      ? translate('preview.frameOf', { index: index + 1, total })
      : translate('preview.frameLabel', { index: index + 1 });
  });

  setCompareMode(mode: PreviewCompareMode): void {
    this.compareMode.set(mode);
  }

  setZoom(zoom: PreviewZoom): void {
    this.zoom.set(zoom);
  }

  syncScroll(source: HTMLElement, target: HTMLElement): void {
    target.scrollTop = source.scrollTop;
    target.scrollLeft = source.scrollLeft;
  }
}
