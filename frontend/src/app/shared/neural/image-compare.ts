import { booleanAttribute, Component, computed, input, model } from '@angular/core';

@Component({
  selector: 'n-image-compare',
  standalone: true,
  template: `
    <figure class="n-image-compare">
      <img class="after" [src]="afterSrc()" [alt]="afterAlt()" />
      <img class="before" [src]="beforeSrc() || afterSrc()" [alt]="beforeAlt()" [style.clip-path]="clipPath()" />
      @if (showLabels()) {
        <span class="label before-label">{{ beforeLabel() }}</span>
        <span class="label after-label">{{ afterLabel() }}</span>
      }
      <i class="divider" [style.left.%]="clampedValue()"></i>
    </figure>
  `,
  styles: [
    `
      .n-image-compare {
        position: relative;
        min-height: 340px;
        aspect-ratio: 16 / 9;
        margin: 0;
        overflow: hidden;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-xl);
        background: #050711;
      }

      img {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .divider {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 2px;
        background: rgba(255, 255, 255, 0.88);
        box-shadow: 0 0 16px rgba(255, 255, 255, 0.35);
        transform: translateX(-50%);
      }

      .label {
        position: absolute;
        top: 16px;
        padding: 7px 13px;
        border-radius: var(--n-radius-full);
        background: rgba(0, 0, 0, 0.62);
        color: var(--n-text-1);
        font-family: var(--n-font-mono);
        font-size: 0.75rem;
        font-weight: 900;
      }

      .before-label {
        left: 16px;
      }

      .after-label {
        right: 16px;
        background: rgba(66, 133, 244, 0.25);
        color: #8ab4ff;
      }
    `,
  ],
})
export class NImageCompare {
  readonly beforeSrc = input('');
  readonly afterSrc = input('');
  readonly beforeAlt = input('Before');
  readonly afterAlt = input('After');
  readonly beforeLabel = input('Before');
  readonly afterLabel = input('After');
  readonly showLabels = input(true, { transform: booleanAttribute });
  readonly value = model(50);

  readonly clampedValue = computed(() => Math.min(Math.max(Number(this.value()) || 50, 0), 100));
  readonly clipPath = computed(() => `inset(0 ${100 - this.clampedValue()}% 0 0)`);
}
