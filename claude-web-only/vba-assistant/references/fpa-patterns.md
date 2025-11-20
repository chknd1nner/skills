# FP&A VBA Automation Patterns

Domain-specific patterns for Financial Planning & Analysis automation. These represent common structures and workflows Sam has encountered across hundreds of companies.

## Variance Analysis Patterns

### Pattern 1: Monthly P&L Variance (Most Common)
**Use case:** Compare current month actuals vs. budget
**Typical structure:**
- Columns: Account Name | Account Code | Actuals | Budget | Variance $ | Variance % | Notes
- Conditional formatting: Red fill for unfavorable variance >10%, yellow for 5-10%
- Account hierarchy: Revenue / COGS / Gross Margin / OpEx / EBITDA / Net Income
- Subtotals at each category level

**VBA approach:** Use Dictionary to map account codes, calculate variances in arrays, apply conditional formatting based on account type (expense accounts reverse the favorable/unfavorable logic)

**Common gotcha:** Expense accounts—a positive variance is actually unfavorable

---

### Pattern 2: YTD Variance with Monthly Detail
**Use case:** Month-end package showing both monthly and year-to-date performance
**Typical structure:**
- Row headers: Account hierarchy
- Column groups: Current Month (Act | Bud | Var$ | Var%) | YTD (Act | Bud | Var$ | Var%)
- Often includes: Prior Year comparison columns

**VBA approach:** Use arrays for performance, group columns with `.Group`, apply formatting by column sets

**Common gotcha:** YTD calculations need to handle partial years correctly (Q1 YTD vs. full year)

---

### Pattern 3: Rolling 12-Month Trend Analysis
**Use case:** Track metrics across rolling 12 months for trend visibility
**Typical structure:**
- Rows: Key metrics (Revenue, Gross Margin %, EBITDA, Headcount)
- Columns: 12 months dynamically updating (oldest month drops off, newest added)
- Often includes: Trend charts, 3-month and 6-month averages

**VBA approach:** Dynamic range management, array rotation to shift months, chart data source updates

---

## Budget Consolidation Patterns

### Pattern 1: Department Budget Roll-up
**Use case:** Consolidate 10-30 department budget files into master budget
**Common challenge:** Each department has slightly different templates, naming conventions
**Typical workflow:**
1. Loop through folder of department files
2. Extract data from standardized range (e.g., B10:M50)
3. Map department-specific account names to corporate chart of accounts
4. Consolidate into master workbook by cost center

**VBA approach:** FileSystemObject for folder iteration, Dictionary for account mapping, error handling for missing files/sheets

**Common gotcha:** Department files locked by users, non-standard fiscal calendars

---

### Pattern 2: Version Control & Change Tracking
**Use case:** Track budget revisions across multiple resubmissions
**Typical structure:**
- Maintain Version 1 (Initial), Version 2 (Revised), Version 3 (Final)
- Delta columns showing changes between versions
- Audit log sheet tracking who changed what and when

**VBA approach:** Copy data to versioned sheets, calculate deltas, log changes with `Environ("username")` and `Now()`

---

## Workday Integration Patterns

### Pattern 1: Workday Actuals Export Processing
**Common export structure:** Account | Account_Name | Cost_Center | CC_Name | Period | Actuals | Currency
**Typical FP&A needs:**
- Convert from long format to P&L layout (rows = accounts, columns = months)
- Map cost centers to department structure
- Handle multi-currency (usually pre-converted, but verify)
- Exclude adjustment periods (Period 13, 14)

**VBA approach:** Dictionary for cost center mapping, Pivot-like transformation using arrays, filter out Period > 12

**Common gotcha:** Workday includes statistical accounts (headcount, FTE) mixed with financials—filter by account type

---

### Pattern 2: Budget Upload Formatting
**Use case:** Format Excel budget data for Workday import template
**Workday import template requirements:**
- Specific column order: Cost_Center | Account | Period | Amount | Currency
- No subtotals or formatting
- Account codes must exactly match Workday chart of accounts
- Date format: YYYY-MM (not MM/DD/YYYY)

**VBA approach:** Unpivot data from budget format (months as columns) to Workday long format, validate account codes against reference list, strip formatting

**Common gotcha:** Workday rejects files with any blank rows or extra columns—must be perfectly clean

---

### Pattern 3: Headcount & Salary Export Processing
**Common export structure:** Employee_ID | Name | Job_Title | Cost_Center | Salary | Benefits | Total_Comp | FTE | Hire_Date
**Typical FP&A needs:**
- Aggregate by department and job level
- Calculate average salary by role
- Track headcount growth vs. budget
- Project future salary expense based on planned hires

**VBA approach:** PivotTable creation via VBA or manual aggregation with arrays, date math for tenure/hire tracking

---

## Salesforce Integration Patterns

### Pattern 1: Opportunity Pipeline Export for Revenue Forecasting
**Common export structure:** Opportunity_ID | Account_Name | Amount | Stage | Probability | Close_Date | Owner
**Typical FP&A needs:**
- Apply weighted probability by stage (e.g., Qualified=20%, Proposal=50%, Negotiation=75%)
- Group by close month for revenue forecast
- Track pipeline coverage ratio (pipeline ÷ quota)
- Split between new business and renewals

**VBA approach:** Dictionary for stage probability mapping, date parsing to fiscal period, weighted calculation: `Amount * Probability`

**Common gotcha:** Close dates slip—FP&A often uses "realistic close date" offset (e.g., +30 days from sales estimate)

---

### Pattern 2: Closed-Won Reconciliation
**Use case:** Reconcile Salesforce closed deals to actual revenue in financials
**Typical workflow:**
1. Export closed-won opportunities for the month
2. Match to revenue transactions in financial system
3. Identify gaps (deals in Salesforce but not in revenue, or vice versa)
4. Create reconciliation report

**VBA approach:** VLOOKUP-style matching using Dictionary, exception reporting for unmatched records

**Common gotcha:** Timing differences (deal closed last day of month but revenue recognized next month), multi-period deals

---

### Pattern 3: Revenue Target Upload
**Use case:** Push FP&A revenue targets back to Salesforce for sales quota management
**Salesforce import requirements:**
- User_ID | Fiscal_Period | Target_Amount | Product_Line
- Must match existing user IDs exactly

**VBA approach:** Map salesperson names to Salesforce User_IDs, validate all IDs exist, format dates to Salesforce fiscal period format

---

## Month-End Close Automation

### Pattern 1: Close Checklist Tracker
**Use case:** Track completion of 30-50 month-end close tasks
**Typical structure:**
- Columns: Task | Owner | Due_Date | Status | Completed_Date | Notes
- Conditional formatting: Overdue tasks red, completed green
- Summary dashboard: % complete, days to close deadline

**VBA approach:** Status dropdown with data validation, auto-timestamp on status change to "Complete", email reminders for overdue tasks

---

### Pattern 2: Journal Entry Template Generator
**Use case:** Create standardized journal entry templates for recurring monthly accruals
**Typical workflow:**
1. Maintain template library (prepaid amortization, accrued expenses, deferrals)
2. Auto-populate with current month values
3. Generate formatted JE ready for system import or review

**VBA approach:** Template storage in hidden sheet, formula replacement with values, formatting for audit trail

**Common gotcha:** Account codes change periodically—maintain reference table for mapping

---

### Pattern 3: Flux Analysis Automation
**Use case:** Automatically identify and explain significant variances month-over-month
**Typical structure:**
- Compare current month to prior month
- Flag accounts with >$50K or >20% variance
- Generate variance explanation template for controllers to complete

**VBA approach:** Calculate month-over-month delta, apply threshold filters, create formatted commentary template with pre-filled account names and variance amounts

---

## Reporting & Dashboard Patterns

### Pattern 1: Executive Summary One-Pager
**Use case:** Generate formatted one-page executive summary from detailed financials
**Typical content:**
- KPIs in scorecard format (Revenue, Margin %, Cash, Headcount)
- Variance to budget (current month and YTD)
- Key highlights and lowlights (top 3 each)
- Trend charts

**VBA approach:** Pull data from detailed sheets, populate template ranges, refresh charts, apply executive-friendly formatting (minimal decimals, $ in thousands)

**Common gotcha:** Charts don't auto-resize well—use fixed positions and scales

---

### Pattern 2: Board Deck Automation
**Use case:** Generate quarterly board presentation slides from financial data
**Typical workflow:**
1. Export data to PowerPoint from Excel
2. Update 15-25 standard slides (financials, metrics, headcount, cash)
3. Apply corporate template formatting

**VBA approach:** Use Excel VBA to automate PowerPoint (requires `CreateObject("PowerPoint.Application")`), copy ranges as pictures or tables, position on slides

**Sam's note:** PowerPoint automation from Excel is painful but possible. Expect position and sizing tweaks.

---

### Pattern 3: Automated Email Distribution
**Use case:** Send monthly financial reports to department managers
**Typical workflow:**
1. Generate department-specific reports (filtered to their cost centers)
2. Save each as PDF
3. Email to respective managers with standard message

**VBA approach:** Loop through department list, apply filter, export to PDF with department name, create Outlook email via VBA

**Common gotcha:** File path length limits (255 chars), Outlook security prompts (may require trust center settings)

---

## Forecast & Planning Patterns

### Pattern 1: Rolling Forecast Update
**Use case:** Update 12-18 month rolling forecast each month
**Typical workflow:**
1. Roll actuals from previous month into forecast
2. Shift forecast periods forward (drop oldest month, add new month at end)
3. Update assumptions (headcount, pricing, seasonality)

**VBA approach:** Array shifting for time periods, formula updates for new columns, maintain version history

---

### Pattern 2: Scenario Planning (Base / Upside / Downside)
**Use case:** Model multiple scenarios with different assumptions
**Typical structure:**
- Three scenario sheets or column sets
- Assumptions table drives each scenario (growth rates, margins, etc.)
- Summary comparison view

**VBA approach:** Link scenarios to assumption drivers, create scenario toggle (dropdown or buttons), consolidated comparison output

---

### Pattern 3: Driver-Based Forecast Model
**Use case:** Forecast revenue based on leading indicators (pipeline, headcount, units)
**Typical drivers:**
- Sales headcount × ramp time × quota attainment
- Marketing spend → leads → conversion rates → deals
- Units sold × average selling price

**VBA approach:** Build calculation engine that flows drivers through logic tree, sensitivity tables for key assumptions

**Common gotcha:** Circular references (e.g., revenue → headcount budget → revenue)—use iterative calculation settings or break circularity

---

## Data Validation & Quality Patterns

### Pattern 1: Pre-Upload Data Validation
**Use case:** Validate budget data before uploading to financial system
**Common checks:**
- All required accounts present
- No negative values in revenue accounts (except returns)
- Total budget matches approved amount
- Department codes valid
- No blank cells in required fields

**VBA approach:** Loop through rules, flag violations with conditional formatting, generate validation report

---

### Pattern 2: Intercompany Elimination Check
**Use case:** Verify intercompany transactions balance to zero
**Typical structure:**
- Intercompany revenue (Entity A) = Intercompany expense (Entity B)
- Track by IC partner and account

**VBA approach:** SUMIF to aggregate by IC partner, compare debits to credits, report imbalances

**Common gotcha:** Timing differences between entities, currency translation impacts

---

## Performance Optimization Notes

**Sam's hard-won lessons from 25+ years:**

1. **Turn off screen updating:** `Application.ScreenUpdating = False` at start, `= True` at end
2. **Use arrays for bulk operations:** Read range to array, process in memory, write back once
3. **Avoid `.Select` and `.Activate`:** Directly reference ranges: `Worksheets("Sheet1").Range("A1").Value = x`
4. **Disable automatic calculation for large models:** `Application.Calculation = xlCalculationManual` during updates
5. **Use `With` blocks:** Reduces object calls: `With Worksheets("Data")` then `.Range("A1")` instead of full path each time
6. **Late binding for external apps:** `CreateObject("Outlook.Application")` instead of early binding to avoid reference issues

**When working with large datasets (>50K rows):**
- Use arrays exclusively
- Consider Power Query instead of VBA (Sam admits this grudgingly)
- Filter data before processing
- Use Dictionary instead of multiple VLOOKUPs

---

**End of FP&A Patterns Reference**

*Sam: "These patterns cover 80% of what I've automated over the years. Your specific company will have variations—just tell me what's different and I'll adapt."*
