package main.java.method;

import java.util.ArrayList;
import java.util.Random;
import main.java.model.Station;
import main.java.model.Device;
import main.java.model.ConstNum;
import main.java.model.Decision;
import main.java.model.Result;

public class AU_SmartGrid_Game {

    public static Result getResult(Station station, ArrayList<Device> devices, Random rad) {

        Result result = new Result();

        System.out.println("Game Start: userNum: "+ devices.size());
        // initialize result
        for(int i=0;i<devices.size();i++) {
            result.getDecisions().add(new Decision());
        }

        //initialize game decisions
        ArrayList<Decision> decisions = new ArrayList<>();
        for(int i=0;i<devices.size();i++) {
            decisions.add(new Decision());
        }

        // initialize players benefit
        for(int i=0;i<devices.size();i++) {
            for(int j=0;j<ConstNum.timeSlots;j++) {
                decisions.get(i).getDc()[j] = 0;
                decisions.get(i).setBenefit(0.0);
                decisions.get(i).getCost()[j] = 0.0;
                decisions.get(i).getSpeed()[j] = 0.0;
            }
        }

        // avg price
        double avgPrice = Station.getAvgPrice(station.getPrice());

        //game part
        while(true) {
            ArrayList<Decision> tempDecisions = getUpdateRequest(station, devices, decisions, result, avgPrice, rad);
            //System.out.println("Decision ready");
            int winner = getWinner(tempDecisions, rad);

            if(winner == -1) {
                break;
            }else {
                Decision previousDecision = decisions.get(winner); //the previous decision: service
                Decision newDecision = tempDecisions.get(winner); //the new decision: Service
                //System.out.println("Winner: " + winner + "PreDecisions: " + previousDecision + "CurDecisions: " + newDecision);
                if(isSameDecision(previousDecision, newDecision)) {
                    continue;
                }
                //update result
                decisions.set(winner, newDecision);
                result.setIteration(result.getIteration()+1);

                //System.out.println("Iter: " +result.getIteration() + " Winner: " + winner + " Benefit: " + decisions.get(winner).getBenefit());
            }
        }
        //calculate the benefit, cost and revenue
        double overallBenefit = 0;
        for(int i=0;i<decisions.size();i++) {
            overallBenefit += decisions.get(i).getBenefit();
        }
        result.setBenefit(overallBenefit);
        result.setDecisions(decisions);

        double revenue = 0;
        revenue = Result.getOverallRevenue(result, station);
        result.setRevenue(revenue);

        return result;
    }

    public static ArrayList<Decision> getUpdateRequest(Station station, ArrayList<Device> devices, ArrayList<Decision> decisions, Result result, double avgPrice, Random rad){
        ArrayList<Decision> tempDecisions = new ArrayList<>();
        for(int i=0;i<decisions.size();i++) {
            tempDecisions.add(new Decision());
            for(int j=0;j<ConstNum.timeSlots;j++) {
                tempDecisions.get(i).setBenefit(0.0);
                tempDecisions.get(i).getDc()[j] = 0;
                tempDecisions.get(i).getSpeed()[j] = 0.0;
                tempDecisions.get(i).getCost()[j] = 0.0;
            }

        }
        for(int i=0;i<devices.size();i++) {

            Decision maxBenefitDecision = FOA_Best_Decision.getFOADecisionPerDevice(station, devices.get(i), decisions, avgPrice, rad);
            //update play_i's update request
            tempDecisions.get(i).setBenefit(maxBenefitDecision.getBenefit());
            tempDecisions.get(i).setDc(maxBenefitDecision.getDc());
            tempDecisions.get(i).setSpeed(maxBenefitDecision.getSpeed());
            tempDecisions.get(i).setCost(maxBenefitDecision.getCost());
        }
        return tempDecisions;
    }

    public static int getWinner(ArrayList<Decision> decisions,Random rad) { // return the userIndex who can be updated
        int winner = -1;

        boolean flag = false;
        for(int i=0;i<decisions.size();i++) {
            if(!Decision.isUnallocated(decisions.get(i))) {
                flag = true;
                break;
            }
        }
        if(flag == false) {
            winner = -1;
        }else {
            //update the decision
            while(true) {
                int index = rad.nextInt(decisions.size());
                if(!Decision.isUnallocated(decisions.get(index))) {
                    winner = index;
                    break;
                }
            }
        }

        return winner;
    }

    public static boolean isSameDecision(Decision decision1, Decision decision2) {
        boolean isSame = true;
        for(int i=0; i<ConstNum.timeSlots; i++) {
            if((decision1.getDc()[i]!= decision2.getDc()[i]) || (decision1.getSpeed()[i]!= decision2.getSpeed()[i])) {
                isSame = false;
            }
        }
        return isSame;
    }
}
