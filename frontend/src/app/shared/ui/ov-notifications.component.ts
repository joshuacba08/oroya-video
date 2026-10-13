import { Component, inject } from '@angular/core';
import { NIcon } from '@neuralangular/angular-ui/icon';

import { TranslatePipe } from '../../core/i18n/translate.pipe';
import { NotificationService } from '../../core/notifications/notification.service';

@Component({
  selector: 'ov-notifications',
  standalone: true,
  imports: [NIcon, TranslatePipe],
  template: `
    <div class="ov-notifications" aria-live="assertive">
      @for (notice of notifications.notices(); track notice.id) {
        <div class="ov-notice" [class]="'ov-notice ov-notice--' + notice.tone" role="alert">
          <n-icon [name]="notice.tone === 'success' ? 'circle-check' : 'alert-circle'" size="sm" />
          <div>
            <strong>{{ notice.title }}</strong>
            <span>{{ notice.message }}</span>
          </div>
          <button
            type="button"
            [attr.aria-label]="'common.close' | t"
            (click)="notifications.dismiss(notice.id)"
          >
            <n-icon name="x" size="sm" />
          </button>
        </div>
      }
    </div>
  `,
  styles: [
    `
      .ov-notifications {
        position: fixed;
        z-index: 1000;
        right: 16px;
        bottom: 16px;
        display: grid;
        gap: 10px;
        width: min(380px, calc(100vw - 32px));
      }

      .ov-notice {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        align-items: start;
        gap: 10px;
        padding: 12px 14px;
        border: 1px solid var(--n-border-1);
        border-radius: var(--n-radius-lg);
        background: var(--n-bg-elevated, #12141f);
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
        color: var(--n-text-2);
        font-size: 0.82rem;
      }

      .ov-notice--danger {
        border-color: color-mix(in srgb, var(--n-color-danger), transparent 55%);
      }

      .ov-notice--danger n-icon {
        color: var(--n-color-danger);
      }

      .ov-notice--success n-icon {
        color: var(--n-color-success);
      }

      .ov-notice div {
        display: grid;
        gap: 2px;
      }

      .ov-notice strong {
        color: var(--n-text-1);
      }

      .ov-notice button {
        border: 0;
        background: transparent;
        color: var(--n-text-3);
        cursor: pointer;
      }
    `,
  ],
})
export class OvNotificationsComponent {
  readonly notifications = inject(NotificationService);
}
