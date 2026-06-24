import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SettingsTabs } from "../../src/features/manager/ManagerDialogs";

export default renderToStaticMarkup(<SettingsTabs />);
