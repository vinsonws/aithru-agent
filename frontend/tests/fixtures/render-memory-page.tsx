import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryContent } from "../../src/features/admin/MemoryPage";

export default renderToStaticMarkup(<MemoryContent />);
