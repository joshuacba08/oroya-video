import { Injectable, inject } from '@angular/core';

import { translate } from '../i18n/i18n';
import type { ModelVm } from '../models/oroya.models';
import { DialogService } from './dialog.service';

/**
 * Modelos con licencia de uso no comercial (GFPGAN): el usuario tiene que aceptarla antes de
 * descargarlos. Los demás se descargan sin preguntar.
 */
@Injectable({ providedIn: 'root' })
export class ModelLicenseService {
  private readonly dialogs = inject(DialogService);

  acceptDownload(model: ModelVm): Promise<boolean> {
    if (!model.nonCommercial) {
      return Promise.resolve(true);
    }
    return this.dialogs.confirm({
      title: translate('model.nonCommercialTitle', { name: model.name }),
      message: translate('model.nonCommercialMessage', { name: model.name }),
      confirmLabel: translate('model.nonCommercialAccept'),
    });
  }
}
